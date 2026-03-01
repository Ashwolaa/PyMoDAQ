"""Top-level DataMixer GUI composition.

Usage
-----
    python -m pymodaq.extensions.data_mixer.gui.data_mixer_gui [path/to/scan.h5]
    # or:
    from pymodaq.extensions.data_mixer.gui.data_mixer_gui import DataMixerGUI, main
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QSplitter, QFileDialog,
    QSpinBox, QComboBox,
)

from pymodaq_data.h5modules.saving import H5SaverLowLevel
from pymodaq_data.data import DataWithAxes
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils.config import GlobalConfig as Config

from pymodaq.extensions.data_mixer.gui.formatters import (
    _collect_h5_names_and_info, _wrap_result,
)
from pymodaq.extensions.data_mixer.gui.variable_browser import VariableBrowserWidget
from pymodaq.extensions.data_mixer.gui.info_panel import InfoPanelWidget
from pymodaq.extensions.data_mixer.gui.console import FormulaConsole, _QTCONSOLE
from pymodaq.extensions.data_mixer.gui.viewer_window import DataViewerWindow
from pymodaq.extensions.data_mixer.parser import (
    extract_data_names,
    replace_names_in_formula_xr,
)

logger = set_logger(get_module_name(__file__))
config = Config()
logger = set_logger(get_module_name(__file__))

from pymodaq_gui.utils.styling import create_icon

class DataMixerGUI(QWidget):
    """Main DataMixer GUI widget.

    Layout
    ------
    QVBoxLayout
      ├── file_row: [Browse] [path QLineEdit] [Load] [mode badge]
      ├── sync_row: [▶ Live Sync] [Interval spinbox] [status label]
      └── QSplitter(Horizontal)
           ├── left_panel  QSplitter(Vertical, ~320 px)
           │    ├── VariableBrowserWidget    (stretch 3)
           │    └── InfoPanelWidget          (stretch 2)
           └── right_panel
                └── FormulaConsole           (stretch 1)

    Threading model
    ---------------
    No background thread.  A ``QTimer`` fires ``_tick()`` in the main thread
    at the configured interval.  ``_tick()`` opens the H5 file, loads only
    new slices for watched datasets, re-evaluates formulas whose inputs
    changed, and closes the file.

    State
    -----
    ``_h5_meta``       dict[str, None]       — rel_path → None  (names only, no data)
    ``_h5_snapshot``   dict[str, xr.Dataset] — rel_path → last loaded dataset
    ``_scan_progress`` int or None           — count of valid Timestamps entries at
                                               the last tick; -1 = never polled;
                                               None = no Timestamps node in file
    ``_deps``          dict[str, set[str]]   — output_name → {input names}
    ``_h5saver_live``  H5SaverLowLevel|None  — kept open for the duration of live sync
    ``_is_swmr_live``  bool                  — whether the live handle is SWMR
    """

    def __init__(self, h5_path: str = '', parent: Optional[QWidget] = None):
        super().__init__(parent)
        # H5 metadata (names only, no data)
        self._h5_meta: dict[str, None] = {}
        self._h5_base: str = '/RawData'
        # Scan-group alias: first-level Scan\d+ groups found in the file
        self._scan_prefixes: list = []
        self._active_scan_prefix: Optional[str] = None
        # Snapshot cache for on-demand and live loads
        self._h5_snapshot: dict = {}           # rel_path → xr.Dataset
        # Live-sync progress marker
        self._scan_progress: Optional[int] = -1  # # of valid Timestamps entries
        # Live-sync file handle (kept open between ticks so refresh_datasets works)
        self._h5saver_live = None
        self._is_swmr_live: bool = False

        # Formula and computed state
        self._xr_ctx_computed: dict = {}   # name → xr.Dataset (computed)
        self._formula_for: dict[str, str] = {}  # var_name → formula text
        self._deps: dict[str, set[str]] = {}    # output_name → {input names}
        self._display_names: set[str] = set()

        # Viewer
        self._viewer_window: Optional[DataViewerWindow] = None

        # Live-sync timer (main thread — no QThread)
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._tick)

        self._setup_ui()

        if h5_path:
            self._path_edit.setText(h5_path)
            self._load_keys()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle('DataMixer GUI')
        self.resize(1280, 800)
        root = QVBoxLayout(self)

        # File row
        file_row = QHBoxLayout()
        browse_btn = QPushButton('Browse')
        browse_btn.clicked.connect(self._browse)
        browse_btn.setIcon(create_icon('folder_data'))
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText('Path to .h5 file …')
        load_btn = QPushButton('Load / Reload')
        load_btn.setToolTip(
            'Scan the H5 file and populate the variable browser.\n'
            'Stored formulas are re-evaluated automatically afterward.')
        load_btn.clicked.connect(self._load_keys)
        load_btn.setIcon(create_icon('refresh'))

        self._refresh_btn = QPushButton('Refresh Tree')
        self._refresh_btn.setToolTip(
            'Rescan the H5 file for new datasets without recomputing formulas.\n'
            'Use this when new scans have been added to the file.\n'
            '(Disabled during live sync — the live handle owns the file.)')
        self._refresh_btn.clicked.connect(self._refresh_tree)
        self._refresh_btn.setIcon(create_icon('account_tree'))

        file_row.addWidget(browse_btn)
        file_row.addWidget(self._path_edit, stretch=1)
        file_row.addWidget(load_btn)
        file_row.addWidget(self._refresh_btn)
        root.addLayout(file_row, 0)

        # Live-sync toolbar row
        sync_row = QHBoxLayout()
        self._sync_btn = QPushButton('▶ Live Sync')
        self._sync_btn.setCheckable(True)
        self._sync_btn.setToolTip(
            'Start/stop periodic refresh of H5 datasets used by stored formulas.'
        )
        self._sync_btn.toggled.connect(self._toggle_live_sync)
        self._sync_icon_start = create_icon('start')
        self._sync_icon_stop  = create_icon('stop_circle')
        self._sync_btn.setIcon(self._sync_icon_start)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(100, 60_000)
        self._interval_spin.setValue(1000)
        self._interval_spin.setSuffix(' ms')
        self._interval_spin.setToolTip('Polling interval for live sync')
        self._interval_spin.valueChanged.connect(self._on_interval_changed)

        self._status_label = QLabel('')
        self._status_label.setStyleSheet('color: #666; font-style: italic;')

        self._scan_combo = QComboBox()
        self._scan_combo.setMinimumWidth(90)
        self._scan_combo.setToolTip(
            'Scan group that {Scan/…} formula references resolve to.\n'
            'Defaults to the most recently written scan (alphabetically last).\n'
            'Click ↻ Reload after a new scan finishes to refresh this list.')
        self._scan_combo.currentTextChanged.connect(self._on_active_scan_changed)

        show_viewers_btn = QPushButton('Show Viewers')
        show_viewers_btn.setToolTip('Raise the floating viewer window to the front')
        show_viewers_btn.clicked.connect(self._raise_viewers)
        show_viewers_btn.setIcon(create_icon('visibility'))

        sync_row.addWidget(self._sync_btn)
        sync_row.addWidget(QLabel('Interval:'))
        sync_row.addWidget(self._interval_spin)
        sync_row.addWidget(self._status_label, stretch=1)
        sync_row.addWidget(QLabel('Active scan:'))
        sync_row.addWidget(self._scan_combo)
        sync_row.addWidget(show_viewers_btn)
        root.addLayout(sync_row, 0)

        # Main horizontal splitter
        h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: browser + info
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)

        self._browser = VariableBrowserWidget()
        self._info_panel = InfoPanelWidget()

        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.addWidget(self._browser)
        v_splitter.addWidget(self._info_panel)
        v_splitter.setStretchFactor(0, 3)
        v_splitter.setStretchFactor(1, 2)
        left_layout.addWidget(v_splitter)

        h_splitter.addWidget(left_widget)

        # Right panel: console
        self._console = FormulaConsole()
        h_splitter.addWidget(self._console)
        h_splitter.setSizes([320, 960])

        root.addWidget(h_splitter, 1)  # stretch=1: splitter takes all remaining height

        # Set console tooltip to show IPython availability (replaces the old mode label)
        mode_text = 'IPython + Editor' if _QTCONSOLE else 'Plain-text editor'
        self._console.setToolTip(f'Formula console  [{mode_text}]')

        # Signal wiring
        self._browser.item_selected_sig.connect(self._on_item_selected)
        self._browser.insert_ref_sig.connect(self._console.insert_at_cursor)
        self._browser.delete_computed_sig.connect(self._on_delete_computed)
        self._browser.show_var_sig.connect(self._on_show_var)
        self._browser.send_formula_sig.connect(self._console.recall_formula)
        self._browser.recompute_all_sig.connect(self._console.recompute_all)
        self._browser.clear_all_computed_sig.connect(self._on_clear_computed)
        self._browser.load_and_show_h5_sig.connect(self._on_load_and_show_h5)
        self._console.variable_stored_sig.connect(self._on_new_variable)
        self._console.clear_computed_sig.connect(self._on_clear_computed)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open H5 file', dir =  config('data','data_saving','h5file','save_path'),
            filter='HDF5 files (*.h5 *.hdf5 *.hdf);;All files (*)')
        if path:
            self._path_edit.setText(path)
            self._load_keys()

    def _on_item_selected(self, ds_name: str, var_name: str) -> None:
        """Display info for the selected item, loading H5 data on demand."""
        if ds_name in self._xr_ctx_computed:
            ds = self._xr_ctx_computed[ds_name]
            source = 'Computed'
            formula = self._formula_for.get(ds_name)
        elif ds_name in self._h5_meta:
            # Load on demand (cached in _h5_snapshot after first load)
            ds = self._load_h5_dataset_for(ds_name)
            source = 'H5'
            formula = None
            if ds is not None:
                self._browser.update_h5_info(ds_name, ds)
        else:
            return
        self._info_panel.display(ds_name, ds, source=source,
                                 formula=formula, var_name=var_name)

    def _on_clear_computed(self) -> None:
        """Full sync clear: browser → GUI state → console (in that order)."""
        self._browser.clear_computed()
        self._xr_ctx_computed.clear()
        self._formula_for.clear()
        self._deps.clear()
        self._console.reset_computed()

    def _on_delete_computed(self, name: str) -> None:
        self._xr_ctx_computed.pop(name, None)
        self._formula_for.pop(name, None)
        self._deps.pop(name, None)
        self._browser.remove_computed(name)
        self._console.remove_computed(name)

    def _on_show_var(self, name: str, display: bool) -> None:
        """Open or close the viewer tab for a computed variable."""
        if display:
            self._display_names.add(name)
            ds = self._xr_ctx_computed.get(name)
            if ds is None:
                return
            try:
                dwa = DataWithAxes.from_xarray(ds)
            except Exception as exc:
                logger.warning(f'Cannot convert {name!r} to DataWithAxes for viewer: {exc}')
                return
            if self._viewer_window is None:
                self._viewer_window = DataViewerWindow()
                self._viewer_window.tab_closed_sig.connect(self._on_viewer_tab_closed)
            self._viewer_window.show_variable(name, dwa)
            self._viewer_window.show()
        else:
            self._display_names.discard(name)
            if self._viewer_window is not None:
                self._viewer_window.remove_variable(name)

    def _on_viewer_tab_closed(self, name: str) -> None:
        """User closed a viewer tab — uncheck the Display checkbox."""
        self._display_names.discard(name)
        self._browser.uncheck_display(name)

    def _on_load_and_show_h5(self, name: str) -> None:
        """Load an H5 dataset on demand and open it in the viewer window."""
        ds = self._load_h5_dataset_for(name)
        if ds is None:
            self._status_label.setText(f'Cannot load {name!r}')
            self._status_label.setStyleSheet('color: #c00; font-style: italic;')
            return
        try:
            dwa = DataWithAxes.from_xarray(ds)
        except Exception as exc:
            logger.warning(f'Cannot convert {name!r} to DataWithAxes for viewer: {exc}')
            return
        if self._viewer_window is None:
            self._viewer_window = DataViewerWindow()
            self._viewer_window.tab_closed_sig.connect(self._on_viewer_tab_closed)
        self._viewer_window.show_variable(name, dwa)
        self._viewer_window.show()
        self._viewer_window.raise_()

    def _raise_viewers(self) -> None:
        """Raise the viewer window to the front, or report if no tabs are open."""
        if self._viewer_window is None or not self._viewer_window.variable_names:
            self._status_label.setText('No viewer tabs open yet')
            self._status_label.setStyleSheet('color: #666; font-style: italic;')
            return
        self._viewer_window.show()
        self._viewer_window.raise_()
        self._viewer_window.activateWindow()

    def _on_interval_changed(self, ms: int) -> None:
        if self._sync_timer.isActive():
            self._sync_timer.setInterval(ms)

    def _toggle_live_sync(self, active: bool) -> None:
        if active:
            path = Path(self._path_edit.text().strip())
            if not path.is_file():
                self._sync_btn.setChecked(False)
                self._status_label.setText('No file loaded')
                return
            # Open file ONCE and keep it open for the duration of live sync.
            # Try SWMR reader first (so refresh_datasets() works on each tick),
            # then fall back to a plain read-only open for non-SWMR files.
            try:
                self._h5saver_live, self._is_swmr_live = \
                    H5SaverLowLevel.open_for_reading(path, force_swmr=True)
            except Exception as exc:
                logger.debug(f'SWMR open failed, trying standard mode: {exc}')
                try:
                    self._h5saver_live, self._is_swmr_live = \
                        H5SaverLowLevel.open_for_reading(path, force_swmr=False)
                except Exception as exc2:
                    self._sync_btn.setChecked(False)
                    self._status_label.setText(f'Cannot open for sync: {exc2}')
                    logger.warning(f'Cannot open {path.name!r} for live sync: {exc2}')
                    return
            # Reset snapshot and progress so the first tick reloads everything.
            self._h5_snapshot.clear()
            self._scan_progress = -1
            self._sync_timer.start(self._interval_spin.value())
            self._sync_btn.setText('■ Live Sync')
            self._sync_btn.setIcon(self._sync_icon_stop)
            self._refresh_btn.setEnabled(False)
            self._status_label.setText('Live sync started')
            # Fire an immediate first tick so existing formulas are evaluated
            # right away rather than waiting for the first timer interval.
            self._tick()
        else:
            self._sync_timer.stop()
            if self._h5saver_live is not None:
                try:
                    self._h5saver_live.close_file()
                except Exception as exc:
                    logger.debug(f'Error closing live H5 handle: {exc}')
                self._h5saver_live = None
            self._sync_btn.setText('▶ Live Sync')
            self._sync_btn.setIcon(self._sync_icon_start)
            self._refresh_btn.setEnabled(True)
            self._status_label.setText('Live sync stopped')

    def _on_new_variable(self, name: str, ds, formula: str) -> None:
        """A computed variable was stored in the console — add to browser."""
        self._xr_ctx_computed[name] = ds
        self._formula_for[name] = formula
        self._browser.add_computed(name, ds)
        self._rebuild_deps()
        if self._sync_timer.isActive():
            # Live sync is running: reset progress so the immediate tick treats
            # the current Timestamps count as "new" and reloads all deps.
            self._scan_progress = -1
            self._tick()
        else:
            # Live sync is off: evaluate immediately against current snapshot.
            self._eval_formulas(set(self._h5_snapshot) | set(self._xr_ctx_computed))
            if name in self._display_names and self._viewer_window is not None:
                updated_ds = self._xr_ctx_computed.get(name)
                if updated_ds is not None:
                    try:
                        dwa = DataWithAxes.from_xarray(updated_ds)
                        self._viewer_window.update(name, dwa)
                    except Exception as exc:
                        logger.warning(f'Viewer update for {name!r} failed: {exc}')

    # ── H5 loading ────────────────────────────────────────────────────────────

    def _refresh_tree(self) -> None:
        """Rescan the H5 file tree and update the browser without recomputing.

        Unlike *Load / Reload*, this method:
        - preserves the snapshot cache (``_h5_snapshot``) so no data is reloaded
        - preserves all computed variables and their formulas
        - only updates the H5-Data section of the browser and autocomplete names

        Useful when new scan groups have been added to the file during an
        acquisition and the user wants to see them without losing current results.
        """
        path = Path(self._path_edit.text().strip())
        if not path.is_file():
            return

        try:
            h5saver, _ = H5SaverLowLevel.open_for_reading(path)
            try:
                h5saver.get_node('/RawData')
                self._h5_base = '/RawData'
            except Exception:
                self._h5_base = '/'
            names, h5_info = _collect_h5_names_and_info(h5saver)
            h5saver.close_file()
        except Exception as exc:
            self._status_label.setText(f'Cannot open: {exc}')
            self._status_label.setStyleSheet('color: #c00; font-style: italic;')
            return

        # Update scan-group combo (new scans may have been added to the file)
        scan_set = sorted(set(
            m.group(0)
            for n in names
            for m in [re.match(r'^Scan\d+', n)]
            if m
        ))
        self._scan_prefixes = scan_set
        self._scan_combo.blockSignals(True)
        self._scan_combo.clear()
        if scan_set:
            self._scan_combo.addItems(scan_set)
            if self._active_scan_prefix in scan_set:
                self._scan_combo.setCurrentText(self._active_scan_prefix)
            else:
                self._active_scan_prefix = scan_set[-1]
                self._scan_combo.setCurrentText(self._active_scan_prefix)
        else:
            self._active_scan_prefix = None
        self._scan_combo.blockSignals(False)

        self._h5_meta = {name: None for name in names}
        self._browser.load_h5(self._h5_meta, info=h5_info)
        self._console.push_h5_context(self._build_h5_context())
        self._console.set_h5_loader(self._load_h5_dataset_for)
        self._status_label.setText('Tree refreshed')
        self._status_label.setStyleSheet('color: #666; font-style: italic;')

    def _load_keys(self) -> None:
        """Re-scan the H5 tree; populate browser with names only (no data)."""
        path = Path(self._path_edit.text().strip())
        if not path.is_file():
            return

        try:
            h5saver, _ = H5SaverLowLevel.open_for_reading(path)
            # Detect the base group
            try:
                h5saver.get_node('/RawData')
                self._h5_base = '/RawData'
            except Exception:
                self._h5_base = '/'
            names, h5_info = _collect_h5_names_and_info(h5saver)
            h5saver.close_file()
        except Exception as exc:
            self._status_label.setText(f'Cannot open: {exc}')
            self._status_label.setStyleSheet('color: #c00; font-style: italic;')
            return

        # Detect scan groups (ScanXXX as first path component)
        scan_set = sorted(set(
            m.group(0)
            for n in names
            for m in [re.match(r'^Scan\d+', n)]
            if m
        ))
        self._scan_prefixes = scan_set
        self._scan_combo.blockSignals(True)
        self._scan_combo.clear()
        if scan_set:
            self._scan_combo.addItems(scan_set)
            self._active_scan_prefix = scan_set[-1]   # most recent = alphabetically last
            self._scan_combo.setCurrentText(self._active_scan_prefix)
        else:
            self._active_scan_prefix = None
        self._scan_combo.blockSignals(False)

        self._h5_meta = {name: None for name in names}
        self._browser.load_h5(self._h5_meta, info=h5_info)
        self._console.push_h5_context(self._build_h5_context())
        self._console.set_h5_loader(self._load_h5_dataset_for)
        self._info_panel.clear()
        self._status_label.setText('')
        self._status_label.setStyleSheet('color: #666; font-style: italic;')

        # Reset snapshot and progress; _eval_formulas will pre-load referenced names
        self._h5_snapshot.clear()
        self._scan_progress = -1

        # If live sync is running, reopen the persistent handle for the (possibly
        # new) file so the timer sees fresh data from the first tick onward.
        if self._sync_timer.isActive():
            if self._h5saver_live is not None:
                try:
                    self._h5saver_live.close_file()
                except Exception:
                    pass
                self._h5saver_live = None
            try:
                self._h5saver_live, self._is_swmr_live = \
                    H5SaverLowLevel.open_for_reading(path, force_swmr=True)
            except Exception as exc:
                logger.debug(f'Cannot reopen {path.name!r} for live sync after reload: {exc}')

        self._rebuild_deps()
        self._eval_formulas(set(self._h5_snapshot) | set(self._xr_ctx_computed))
        # Re-run stored formulas so the user sees up-to-date results immediately.
        # recompute_all() does a validation pass then re-evaluates in order, which
        # is more thorough than _eval_formulas (it re-parses formula text).
        if self._formula_for:
            self._console.recompute_all()

    def _build_h5_context(self) -> dict:
        """Return the context dict to push to the formula console.

        Contains all real H5 names **plus** ``Scan/…`` aliases for every
        dataset under the active scan prefix.  The aliases let users write
        portable formulas like ``{Scan/Detector000/Data0D/CH00}`` that
        automatically follow whichever scan is selected in the combobox.
        """
        ctx: dict = dict(self._h5_meta)
        if self._active_scan_prefix:
            prefix = self._active_scan_prefix + '/'
            for name in self._h5_meta:
                if name.startswith(prefix):
                    alias = 'Scan/' + name[len(prefix):]
                    ctx[alias] = None
        return ctx

    def _on_active_scan_changed(self, prefix: str) -> None:
        """User selected a different scan in the combobox — rewire aliases."""
        if not prefix or prefix == self._active_scan_prefix:
            return
        self._active_scan_prefix = prefix
        # Invalidate cached Scan/ snapshots (they now point to the old scan)
        for key in list(self._h5_snapshot):
            if key.startswith('Scan/'):
                del self._h5_snapshot[key]
        # Push updated alias context to the console (autocomplete + validation)
        self._console.push_h5_context(self._build_h5_context())
        self._console.set_h5_loader(self._load_h5_dataset_for)
        # Re-evaluate formulas that reference Scan/…
        self._rebuild_deps()
        self._eval_formulas(set(self._h5_snapshot) | set(self._xr_ctx_computed))

    # ── On-demand H5 loading ─────────────────────────────────────────────────

    def _load_h5_dataset_for(self, rel_path: str):
        """Load *rel_path* from the H5 file and cache it in ``_h5_snapshot``.

        Called on demand (info panel click, formula evaluation) and by the
        incremental loader.  Returns the ``xr.Dataset`` or ``None`` on failure.

        ``Scan/…`` aliases are transparently resolved to the path under the
        currently active scan prefix (``_active_scan_prefix``).
        """
        # Resolve Scan/ alias → actual rel_path
        actual_rel = rel_path
        if rel_path.startswith('Scan/') and self._active_scan_prefix:
            actual_rel = self._active_scan_prefix + '/' + rel_path[len('Scan/'):]
            if actual_rel in self._h5_snapshot:
                self._h5_snapshot[rel_path] = self._h5_snapshot[actual_rel]
                return self._h5_snapshot[rel_path]

        # Return cached value if already loaded
        if rel_path in self._h5_snapshot:
            return self._h5_snapshot[rel_path]

        path = Path(self._path_edit.text().strip())
        if not path.is_file():
            return None

        from pymodaq_data.h5modules.data_saving import DataLoader
        from pymodaq_data.h5modules.backends import GROUP

        try:
            h5saver, _ = H5SaverLowLevel.open_for_reading(path, force_swmr=True)
            try:
                abs_path = f'{self._h5_base}/{actual_rel}'.replace('//', '/')
                # Find the first data array in the group
                first_array_path = None
                for node in h5saver.walk_nodes(abs_path):
                    if isinstance(node, GROUP):
                        continue
                    try:
                        dt = node.attrs['data_type']
                        if 'data' in str(dt):
                            first_array_path = node.path
                            break
                    except Exception:
                        continue
                if first_array_path is None:
                    return None
                loader = DataLoader(h5saver)
                dwa = loader.load_data(first_array_path, load_all=True)
                ds = dwa.to_xarray()
                self._h5_snapshot[actual_rel] = ds
                if actual_rel != rel_path:
                    self._h5_snapshot[rel_path] = ds   # alias → same object
                return ds
            finally:
                try:
                    h5saver.close_file()
                except Exception as exc:
                    logger.debug(f'Error closing H5 handle after dataset load: {exc}')
        except Exception as exc:
            logger.warning(f'Failed to load H5 dataset {rel_path!r}: {exc}')
            return None

    # ── Timer-based live sync ─────────────────────────────────────────────────

    def _tick(self) -> None:
        """Called by QTimer in the main thread; poll H5 and recompute.

        Change detection
        ----------------
        PyMoDAQ pre-allocates scan arrays at the start of a scan, so array
        length never changes during acquisition.  Instead, progress is tracked
        via the **Timestamps** (or ElapsedTime) node: PyMoDAQ fills this array
        with NaN for pending scan points and writes the elapsed time as each
        point completes.  The count of non-NaN entries is a reliable, monotone
        progress indicator.

        If no Timestamps node is found in the file (manually created H5), the
        tick always reloads — a safe but less efficient fallback.
        """
        if self._h5saver_live is None:
            return

        # Collect H5 datasets referenced by stored formulas (real paths + Scan/ aliases)
        effective_watched: set = set()
        for formula in self._formula_for.values():
            try:
                for name in extract_data_names(formula):
                    if name in self._h5_meta or (
                            name.startswith('Scan/') and self._active_scan_prefix):
                        effective_watched.add(name)
            except Exception as exc:
                logger.warning(f'Cannot parse formula deps during tick: {exc}')

        if not effective_watched:
            return

        # SWMR: refresh metadata so the reader sees new rows
        if self._is_swmr_live:
            try:
                from pymodaq_data.h5modules.swmr import refresh_datasets
                refresh_datasets(self._h5saver_live.h5file)
            except Exception as exc:
                logger.debug(f'SWMR refresh failed: {exc}')

        # Check scan progress via Timestamps
        progress = self._read_scan_progress(self._h5saver_live)
        # None means no Timestamps node — always reload.
        # -1 means first tick — always load.
        # Otherwise skip if the count hasn't changed.
        if progress is not None and progress == self._scan_progress:
            return
        self._scan_progress = progress

        # Reload all formula deps from the live handle
        changed: set = set()
        for rel_path in effective_watched:
            ds = self._load_dataset_live(self._h5saver_live, rel_path)
            if ds is not None:
                self._h5_snapshot[rel_path] = ds
                changed.add(rel_path)

        if changed:
            self._eval_formulas(changed)
            self._status_label.setText(f'Synced {time.strftime("%H:%M:%S")}')

    def _read_scan_progress(self, h5saver) -> Optional[int]:
        """Count completed scan points via the Timestamps/ElapsedTime node.

        Uses the node's actual HDF5 fill value (via :meth:`_node_fill_value`)
        to distinguish written entries from pre-allocated placeholders.  This
        handles fill values of NaN, 0, or any custom sentinel set in the scan
        settings — not just NaN.

        Returns ``None`` if no Timestamps/ElapsedTime node is found (the
        caller will reload unconditionally in that case).
        """
        from pymodaq_data.h5modules.backends import GROUP
        try:
            for node in h5saver.walk_nodes('/'):
                if isinstance(node, GROUP):
                    continue
                node_name = node.name.split('/')[-1]
                if 'Timestamp' in node_name or 'ElapsedTime' in node_name:
                    data = np.asarray(node[:]).flatten().astype(float)
                    fill_val = self._node_fill_value(node)
                    if fill_val is None or np.isnan(float(fill_val)):
                        valid = np.isfinite(data)
                    else:
                        valid = data != float(fill_val)
                    return int(np.sum(valid))
        except Exception as exc:
            logger.debug(f'Could not read scan progress from Timestamps node: {exc}')
        return None

    @staticmethod
    def _node_fill_value(node):
        """Return the fill/default value stored in the H5 backend node.

        Tries (in order):
        * ``node.fillvalue``  — h5py Dataset attribute
        * ``node.atom.dflt``  — PyTables EArray/CArray atom default
        * ``None``            — unknown; caller should fall back to NaN/isfinite
        """
        try:
            fv = node.fillvalue
            if fv is not None:
                return fv
        except AttributeError:
            pass
        try:
            return node.atom.dflt
        except AttributeError:
            pass
        return None

    def _load_dataset_live(self, h5saver, rel_path: str):
        """Load *rel_path* fresh from the live H5 handle.

        Bypasses ``_h5_snapshot`` — the caller is responsible for updating it.

        The full pre-allocated array is returned, including NaN (or the scan
        fill value) for not-yet-written scan points.  Formulas that aggregate
        across the scan axis should use NaN-aware operations (e.g.
        ``np.nanmean``) to operate only on the completed entries.

        ``Scan/…`` aliases are resolved to the active scan prefix before
        building the absolute H5 path.

        Returns the ``xr.Dataset`` or ``None`` on failure.
        """
        from pymodaq_data.h5modules.data_saving import DataLoader
        from pymodaq_data.h5modules.backends import GROUP

        actual_rel = rel_path
        if rel_path.startswith('Scan/') and self._active_scan_prefix:
            actual_rel = self._active_scan_prefix + '/' + rel_path[len('Scan/'):]

        abs_path = f'{self._h5_base}/{actual_rel}'.replace('//', '/')
        try:
            first_array_path = None
            for node in h5saver.walk_nodes(abs_path):
                if isinstance(node, GROUP):
                    continue
                try:
                    if 'data' in str(node.attrs['data_type']):
                        first_array_path = node.path
                        break
                except Exception:
                    continue
            if first_array_path is None:
                return None
            loader = DataLoader(h5saver)
            dwa = loader.load_data(first_array_path, load_all=True)
            return dwa.to_xarray()
        except Exception as exc:
            logger.warning(f'Live load failed for {rel_path!r}: {exc}')
            return None

    # ── Formula evaluation ────────────────────────────────────────────────────

    def _rebuild_deps(self) -> None:
        """Rebuild ``output_name → {input names}`` map from ``_formula_for``."""
        self._deps = {}
        for name, formula in self._formula_for.items():
            try:
                self._deps[name] = set(extract_data_names(formula))
            except Exception as exc:
                logger.warning(f'Cannot parse deps for formula {name!r}: {exc}')
                self._deps[name] = set()

    def _eval_formulas(self, changed: set) -> None:
        """Evaluate formulas whose deps intersect *changed*; update browser + viewer.

        ``changed`` is a set of names (rel_paths for H5, output names for
        chained computed vars) that have fresh data.

        The evaluation context is ``_h5_snapshot`` (watched H5 data) merged
        with ``_xr_ctx_computed`` (previous computed results).
        """
        import xarray as xr

        if not self._formula_for:
            return

        # Pre-load any referenced H5 datasets not yet in the snapshot.
        # A freshly loaded dataset is treated as changed so the formula is
        # evaluated immediately rather than waiting for the next tick.
        for formula in self._formula_for.values():
            try:
                for name in extract_data_names(formula):
                    is_h5 = name in self._h5_meta or (
                        name.startswith('Scan/') and self._active_scan_prefix is not None)
                    if is_h5 and name not in self._h5_snapshot:
                        self._load_h5_dataset_for(name)
                        if name in self._h5_snapshot:
                            changed.add(name)
            except Exception as exc:
                logger.warning(f'Cannot pre-load formula deps: {exc}')

        xr_ctx: dict = {**self._h5_snapshot, **self._xr_ctx_computed}
        computed_names = set(self._xr_ctx_computed)

        for name, formula in self._formula_for.items():
            deps = self._deps.get(name, set())
            # Skip formulas whose inputs haven't changed (unless no dep info)
            if deps and not (deps & changed):
                continue

            try:
                formula_eval, _ = replace_names_in_formula_xr(
                    formula, computed_names=computed_names,
                )
                result = eval(formula_eval, {'np': np, 'xr': xr, '_xr': xr_ctx})
                dwa = _wrap_result(result, name)

                # Store result so chained formulas can reference it
                if isinstance(result, xr.DataArray):
                    ds_result = result.to_dataset(name=name)
                elif isinstance(result, xr.Dataset):
                    ds_result = result
                else:
                    ds_result = dwa.to_xarray()

                self._xr_ctx_computed[name] = ds_result
                self._console.update_computed_live(name, ds_result)
                xr_ctx[name] = ds_result  # make available to later formulas
                changed.add(name)         # downstream formulas may depend on this

                self._browser.update_computed_info(name, ds_result)
                if name in self._display_names and self._viewer_window is not None:
                    self._viewer_window.update(name, dwa)

            except Exception as exc:
                self._status_label.setText(f'Formula "{name}": {exc}')
                self._status_label.setStyleSheet('color: #c00; font-style: italic;')

    # ── public API ────────────────────────────────────────────────────────────

    def connect_to_daq_scan(self, daq_scan) -> None:
        """Hook into a running DAQScan for point-by-point recompute.

        Each new scan point triggers an immediate tick (no timer wait).
        """
        try:
            daq_scan.scan_acquisition.scan_data_tmp.connect(
                self._on_scan_data_temp
            )
        except Exception as exc:
            logger.warning(f'Cannot connect to DAQScan scan_data_tmp signal: {exc}')

    def disconnect_from_daq_scan(self, daq_scan) -> None:
        try:
            daq_scan.scan_acquisition.scan_data_tmp.disconnect(
                self._on_scan_data_temp
            )
        except Exception as exc:
            logger.debug(f'Cannot disconnect from DAQScan scan_data_tmp signal: {exc}')

    def _on_scan_data_temp(self, scan_data) -> None:
        """New scan point arrived; trigger an immediate tick."""
        self._tick()

    def closeEvent(self, event) -> None:
        self._sync_timer.stop()
        if self._h5saver_live is not None:
            try:
                self._h5saver_live.close_file()
            except Exception as exc:
                logger.debug(f'Error closing live H5 handle on exit: {exc}')
            self._h5saver_live = None
        if self._viewer_window is not None:
            self._viewer_window.close()
        super().closeEvent(event)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    h5_path = sys.argv[1] if len(sys.argv) > 1 else ''
    w = DataMixerGUI(h5_path)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
