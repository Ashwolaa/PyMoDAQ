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
from typing import Optional, Union

import numpy as np
from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QApplication, QWidget, QSplitter, QFileDialog, QMainWindow,
)

from pymodaq_data.h5modules.saving import H5SaverLowLevel
from pymodaq_data.data import DataWithAxes
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils.config import GlobalConfig as Config

from pymodaq_gui.utils.dock import DockArea, Dock

from pymodaq.extensions.custom_ext import CustomExt
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


class DataMixerGUI(CustomExt):
    """Main DataMixer GUI — inherits from CustomExt for Dashboard integration.

    Layout (DockArea)
    -----------------
    dock_settings  [left]              — settings parameter tree
    dock_browser   [right of settings] — VariableBrowserWidget + InfoPanelWidget
    dock_console   [right of browser]  — FormulaConsole
    dock_viewer    [right of console]  — DataViewerWindow (QTabWidget)

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

    params = [
        {'title': 'H5 file', 'name': 'h5_path', 'type': 'browsepath', 'value': ''},
        {'title': 'File info', 'name': 'file_info', 'type': 'group', 'children': [
            {'title': 'Backend',  'name': 'backend',   'type': 'str',
             'value': '—', 'readonly': True},
            {'title': 'SWMR live', 'name': 'swmr_mode', 'type': 'led', 'value': False, 'readonly': True},
            {'title': 'Scans',    'name': 'n_scans',   'type': 'int',
             'value': 0,   'readonly': True},
            {'title': 'Size',     'name': 'file_size', 'type': 'str',
             'value': '—', 'readonly': True},
        ]},
        {'title': 'Live sync', 'name': 'live_sync', 'type': 'group', 'children': [
            {'title': 'Active',        'name': 'live_led',        'type': 'led',    'value': False, 'readonly': True},
            {'title': 'Interval (ms)', 'name': 'interval',        'type': 'int',
             'value': 1000, 'min': 100, 'max': 60000},
            {'title': 'Active scan',   'name': 'active_scan',     'type': 'list',   'limits': []},
            {'title': 'Use latest',    'name': 'use_latest_scan', 'type': 'action'},
        ]},
    ]

    def __init__(self, dockarea: Union[DockArea, QMainWindow, QWidget],
                 dashboard=None):
        # Initialise plain Python state BEFORE super().__init__() because
        # setup_docks / setup_actions / connect_things are called inside
        # setup_ui() which is triggered explicitly below.
        self._h5_meta: dict = {}
        self._h5_base: str = '/RawData'
        self._scan_prefixes: list = []
        self._active_scan_prefix: Optional[str] = None
        self._h5_snapshot: dict = {}
        self._scan_progress: Optional[int] = -1
        self._h5saver_live = None
        self._is_swmr_live: bool = False

        self._xr_ctx_computed: dict = {}
        self._formula_for: dict = {}
        self._deps: dict = {}
        self._display_names: set = set()

        super().__init__(dockarea, dashboard)
        self.setup_ui()

        # QTimer needs self (QObject) to exist — safe after super().__init__()
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._tick)

    # ── CustomApp mandatory overrides ─────────────────────────────────────────

    def setup_docks(self) -> None:
        if self.dashboard is not None:
            self.create_dashboard_toolbar()

        # --- Settings dock (far left) ---
        self.docks['settings'] = Dock('Settings')
        self.dockarea.addDock(self.docks['settings'])
        self.docks['settings'].addWidget(self.settings_tree)

        # --- Variable browser + info panel ---
        self.docks['browser'] = Dock('Variables')
        self.dockarea.addDock(self.docks['browser'], 'right',
                              self.docks['settings'])
        self._browser = VariableBrowserWidget()
        self._info_panel = InfoPanelWidget()
        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.addWidget(self._browser)
        v_split.addWidget(self._info_panel)
        v_split.setStretchFactor(0, 3)
        v_split.setStretchFactor(1, 2)
        self.docks['browser'].addWidget(v_split)

        # --- Formula console ---
        self.docks['console'] = Dock('Formula Console')
        self.dockarea.addDock(self.docks['console'], 'right',
                              self.docks['browser'])
        self._console = FormulaConsole()
        self.docks['console'].addWidget(self._console)

        # --- Data viewer ---
        self.docks['viewer'] = Dock('Data Viewer')
        self.dockarea.addDock(self.docks['viewer'], 'right',
                              self.docks['console'])
        self._viewer_widget = DataViewerWindow()
        self._viewer_widget.tab_closed_sig.connect(self._on_viewer_tab_closed)
        self.docks['viewer'].addWidget(self._viewer_widget)

    def setup_actions(self) -> None:
        _theme = self.get_theme()
        _green = _theme.green if _theme is not None else None
        _red = _theme.red if _theme is not None else None
        self.add_action('show_settings', 'Show Settings', 'settings',
                        'Show/hide the settings panel',
                        checkable=True, checked=True,
                        icon_checked_color=_green)
        self.add_action('browse', 'Browse', 'folder_data', 'Open H5 file')
        self.add_action('load', 'Load / Reload', 'refresh',
                        'Scan the H5 file and populate the variable browser.\n'
                        'Stored formulas are re-evaluated automatically afterward.',
                        icon_color=_green)
        self.add_action('refresh_tree', 'Refresh Tree', 'account_tree',
                        'Rescan the H5 file for new datasets without recomputing formulas.\n'
                        'Use this when new scans have been added to the file.\n'
                        '(Disabled during live sync — the live handle owns the file.)')
        self.add_action('live_sync', 'Live Sync', 'start',
                        'Start/stop periodic refresh of H5 datasets used by stored formulas.',
                        checkable=True, icon_checked='stop_circle',
                        icon_color=_green,
                        icon_checked_color=_red)
        self.add_action('show_viewer', 'Show Viewer', 'visibility',
                        'Raise the Data Viewer dock')

    def connect_things(self) -> None:
        self.connect_action('show_settings', self._toggle_settings_dock)
        self.connect_action('browse', self._browse)
        self.connect_action('load', self._load_keys)
        self.connect_action('refresh_tree', self._refresh_tree)
        self.connect_action('live_sync', self._toggle_live_sync)
        self.connect_action('show_viewer', self._raise_viewers)

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

        self.settings.child('live_sync', 'use_latest_scan').sigActivated.connect(
            self._go_to_latest_scan
        )

    def do_things_after_ui_setup(self) -> None:
        mode_text = 'IPython + Editor' if _QTCONSOLE else 'Plain-text editor'
        self._console.setToolTip(f'Formula console  [{mode_text}]')

    def value_changed(self, param) -> None:
        if param.name() == 'h5_path':
            pass  # user may trigger Load manually
        elif param.name() == 'interval':
            if self._sync_timer.isActive():
                self._sync_timer.setInterval(param.value())
        elif param.name() == 'active_scan':
            self._on_active_scan_changed(param.value())

    def quit_fun(self) -> None:
        self._sync_timer.stop()
        if self._h5saver_live is not None:
            try:
                self._h5saver_live.close_file()
            except Exception as exc:
                logger.debug(f'Error closing live H5 handle on exit: {exc}')
            self._h5saver_live = None
        super().quit_fun()

    # ── status bar helper ─────────────────────────────────────────────────────

    def _set_status(self, msg: str, error: bool = False) -> None:
        """Show a message in the status bar (if available) or log it."""
        if self.statusbar is not None:
            self.statusbar.showMessage(msg)
        else:
            if error:
                logger.warning(msg)
            else:
                logger.info(msg)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _toggle_settings_dock(self, show: bool) -> None:
        """Show or hide the Settings dock (mirrors the standard module behaviour)."""
        self.docks['settings'].setVisible(show)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.mainwindow, 'Open H5 file',
            dir=config('data', 'data_saving', 'h5file', 'save_path'),
            filter='HDF5 files (*.h5 *.hdf5 *.hdf);;All files (*)')
        if path:
            self.settings.child('h5_path').setValue(path)
            self._load_keys()

    def _on_item_selected(self, ds_name: str, var_name: str) -> None:
        """Display info for the selected item, loading H5 data on demand."""
        if ds_name in self._xr_ctx_computed:
            ds = self._xr_ctx_computed[ds_name]
            source = 'Computed'
            formula = self._formula_for.get(ds_name)
        elif ds_name in self._h5_meta:
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
            if self._show_ds_in_viewer(name, ds):
                self.docks['viewer'].setVisible(True)
        else:
            self._display_names.discard(name)
            self._viewer_widget.remove_variable(name)

    def _on_viewer_tab_closed(self, name: str) -> None:
        """User closed a viewer tab — uncheck the Display checkbox."""
        self._display_names.discard(name)
        self._browser.uncheck_display(name)

    def _on_load_and_show_h5(self, name: str) -> None:
        """Load an H5 dataset on demand and open it in the viewer dock."""
        ds = self._load_h5_dataset_for(name)
        if ds is None:
            self._set_status(f'Cannot load {name!r}', error=True)
            return
        if self._show_ds_in_viewer(name, ds):
            self._raise_viewers()

    def _raise_viewers(self) -> None:
        """Raise the Data Viewer dock to the front."""
        if not self._viewer_widget.variable_names:
            self._set_status('No viewer tabs open yet')
            return
        self.docks['viewer'].setVisible(True)
        self.docks['viewer'].raise_()

    def _toggle_live_sync(self, active: bool) -> None:
        if active:
            path = Path(self.settings.child('h5_path').value().strip())
            if not path.is_file():
                self.set_action_checked('live_sync', False)
                self._set_status('No file loaded')
                return
            try:
                self._h5saver_live, self._is_swmr_live = \
                    H5SaverLowLevel.open_for_reading(path, force_swmr=True)
            except Exception as exc:
                logger.debug(f'SWMR open failed, trying standard mode: {exc}')
                try:
                    self._h5saver_live, self._is_swmr_live = \
                        H5SaverLowLevel.open_for_reading(path, force_swmr=False)
                except Exception as exc2:
                    self.set_action_checked('live_sync', False)
                    self._set_status(f'Cannot open for sync: {exc2}', error=True)
                    logger.warning(f'Cannot open {path.name!r} for live sync: {exc2}')
                    return
            self._h5_snapshot.clear()
            self._scan_progress = -1
            self._sync_timer.start(self.settings.child('live_sync', 'interval').value())
            # Lock file-selection controls so the live handle stays consistent
            self.set_action_enabled('browse', False)
            self.set_action_enabled('load', False)
            self.set_action_enabled('refresh_tree', False)
            self.settings.child('h5_path').setOpts(readonly=True)
            self.settings.child('live_sync', 'live_led').setValue(True)
            self.settings.child('file_info', 'swmr_mode').setValue(self._is_swmr_live)
            self._set_status('Live sync started')
            self._tick()
        else:
            self._sync_timer.stop()
            self.settings.child('live_sync', 'live_led').setValue(False)
            if self._h5saver_live is not None:
                try:
                    self._h5saver_live.close_file()
                except Exception as exc:
                    logger.debug(f'Error closing live H5 handle: {exc}')
                self._h5saver_live = None
            # Unlock file-selection controls
            self.set_action_enabled('browse', True)
            self.set_action_enabled('load', True)
            self.set_action_enabled('refresh_tree', True)
            self.settings.child('h5_path').setOpts(readonly=False)
            self._set_status('Live sync stopped')

    def _on_new_variable(self, name: str, ds, formula: str) -> None:
        """A computed variable was stored in the console — add to browser."""
        self._xr_ctx_computed[name] = ds
        self._formula_for[name] = formula
        self._browser.add_computed(name, ds)
        self._rebuild_deps()
        if self._sync_timer.isActive():
            self._scan_progress = -1
            self._tick()
        else:
            self._eval_formulas(set(self._h5_snapshot) | set(self._xr_ctx_computed))
            if name in self._display_names:
                updated_ds = self._xr_ctx_computed.get(name)
                if updated_ds is not None:
                    try:
                        dwa = DataWithAxes.from_xarray(updated_ds)
                        self._viewer_widget.update(name, dwa)
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
        path = Path(self.settings.child('h5_path').value().strip())
        if not path.is_file():
            return
        result = self._scan_h5_file(path)
        if result is None:
            return
        names, h5_info, scan_set = result
        self._update_active_scan(scan_set, preserve=True)
        self._apply_tree_scan(names, h5_info)
        self._set_status('Tree refreshed')

    def _load_keys(self) -> None:
        """Re-scan the H5 tree; populate browser with names only (no data)."""
        path = Path(self.settings.child('h5_path').value().strip())
        if not path.is_file():
            return
        result = self._scan_h5_file(path)
        if result is None:
            return
        names, h5_info, scan_set = result
        self._update_active_scan(scan_set, preserve=False)
        self._apply_tree_scan(names, h5_info)
        self._info_panel.clear()
        self._set_status('')

        self._h5_snapshot.clear()
        self._scan_progress = -1

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
                logger.debug(
                    f'Cannot reopen {path.name!r} for live sync after reload: {exc}')

        self._rebuild_deps()
        self._eval_formulas(set(self._h5_snapshot) | set(self._xr_ctx_computed))
        if self._formula_for:
            self._console.recompute_all()

    def _go_to_latest_scan(self) -> None:
        """Select the most recently added scan as the active scan."""
        if not self._scan_prefixes:
            self._set_status('No scans available')
            return
        self.settings.child('live_sync', 'active_scan').setValue(self._scan_prefixes[-1])

    def _update_file_info(self, path: Path, h5saver) -> None:
        """Populate the File info settings group from an open *h5saver* handle.

        Called at the end of :meth:`_load_keys` and :meth:`_refresh_tree`
        while the handle is still open so that backend detection works.
        SWMR status is shown as False here and updated by
        :meth:`_toggle_live_sync` once the live handle is actually opened.
        """
        try:
            mod = type(h5saver.h5file).__module__
            if 'h5py' in mod:
                backend = 'h5py'
            elif 'tables' in mod:
                backend = 'PyTables'
            else:
                backend = mod.split('.')[0]
        except Exception:
            backend = '?'

        try:
            nb = path.stat().st_size
            if nb >= 1_073_741_824:
                size_str = f'{nb / 1_073_741_824:.2f} GB'
            elif nb >= 1_048_576:
                size_str = f'{nb / 1_048_576:.2f} MB'
            else:
                size_str = f'{nb / 1024:.1f} KB'
        except Exception:
            size_str = '?'

        self.settings.child('file_info', 'backend').setValue(backend)
        self.settings.child('file_info', 'swmr_mode').setValue(False)
        self.settings.child('file_info', 'n_scans').setValue(len(self._scan_prefixes))
        self.settings.child('file_info', 'file_size').setValue(size_str)

    def _scan_h5_file(self, path: 'Path') -> 'Optional[tuple]':
        """Open *path*, walk H5 nodes and return ``(names, h5_info, scan_set)``.

        Updates ``_h5_base`` and ``_scan_prefixes`` as a side-effect.
        Returns ``None`` on error (status message already set).
        """
        try:
            h5saver, _ = H5SaverLowLevel.open_for_reading(path)
            try:
                h5saver.get_node('/RawData')
                self._h5_base = '/RawData'
            except Exception:
                self._h5_base = '/'
            names, h5_info = _collect_h5_names_and_info(h5saver)
            scan_set = sorted(set(
                m.group(0)
                for n in names
                for m in [re.match(r'^Scan\d+', n)]
                if m
            ))
            self._scan_prefixes = scan_set
            self._update_file_info(path, h5saver)
            h5saver.close_file()
        except Exception as exc:
            self._set_status(f'Cannot open: {exc}', error=True)
            return None
        return names, h5_info, scan_set

    def _update_active_scan(self, scan_set: list, preserve: bool) -> None:
        """Sync the *active_scan* param with *scan_set*.

        When *preserve* is ``True`` the current selection is kept if it is
        still present in *scan_set* (used by ``_refresh_tree``).
        When *preserve* is ``False`` (used by ``_load_keys``) the last scan
        in *scan_set* is always selected.
        """
        self.settings.child('live_sync', 'active_scan').setLimits(scan_set)
        if scan_set:
            if preserve and self._active_scan_prefix in scan_set:
                self.settings.child('live_sync', 'active_scan').setValue(
                    self._active_scan_prefix)
            else:
                self._active_scan_prefix = scan_set[-1]
                self.settings.child('live_sync', 'active_scan').setValue(
                    self._active_scan_prefix)
        else:
            self._active_scan_prefix = None

    def _apply_tree_scan(self, names: list, h5_info: dict) -> None:
        """Populate ``_h5_meta``, browser and console from a fresh tree scan."""
        self._h5_meta = {name: None for name in names}
        self._browser.load_h5(self._h5_meta, info=h5_info)
        self._console.push_h5_context(self._build_h5_context())
        self._console.set_h5_loader(self._load_h5_dataset_for)

    def _resolve_scan_alias(self, rel_path: str) -> str:
        """Resolve a ``Scan/…`` alias to the active scan prefix, or return unchanged."""
        if rel_path.startswith('Scan/') and self._active_scan_prefix:
            return self._active_scan_prefix + '/' + rel_path[len('Scan/'):]
        return rel_path

    @staticmethod
    def _load_dwa_from_node(h5saver, abs_path: str):
        """Walk *abs_path* in *h5saver*, find the first data array, load as xr.Dataset.

        Returns the ``xr.Dataset`` or ``None`` if no data node is found.
        """
        from pymodaq_data.h5modules.data_saving import DataLoader
        from pymodaq_data.h5modules.backends import GROUP

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

    def _show_ds_in_viewer(self, name: str, ds) -> bool:
        """Convert *ds* to DataWithAxes and open/update a viewer tab for *name*.

        Returns ``True`` on success, ``False`` if conversion fails.
        """
        try:
            dwa = DataWithAxes.from_xarray(ds)
        except Exception as exc:
            logger.warning(f'Cannot convert {name!r} to DataWithAxes for viewer: {exc}')
            return False
        self._viewer_widget.show_variable(name, dwa)
        return True

    def _build_h5_context(self) -> dict:
        """Return the context dict to push to the formula console.

        Contains all real H5 names **plus** ``Scan/…`` aliases for every
        dataset under the active scan prefix.  The aliases let users write
        portable formulas like ``{Scan/Detector000/Data0D/CH00}`` that
        automatically follow whichever scan is selected in the params tree.
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
        """User selected a different scan — rewire aliases."""
        if not prefix or prefix == self._active_scan_prefix:
            return
        self._active_scan_prefix = prefix
        for key in list(self._h5_snapshot):
            if key.startswith('Scan/'):
                del self._h5_snapshot[key]
        self._console.push_h5_context(self._build_h5_context())
        self._console.set_h5_loader(self._load_h5_dataset_for)
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
        actual_rel = self._resolve_scan_alias(rel_path)
        if actual_rel in self._h5_snapshot:
            if actual_rel != rel_path:
                self._h5_snapshot[rel_path] = self._h5_snapshot[actual_rel]
            return self._h5_snapshot[actual_rel]

        if rel_path in self._h5_snapshot:
            return self._h5_snapshot[rel_path]

        path = Path(self.settings.child('h5_path').value().strip())
        if not path.is_file():
            return None

        try:
            h5saver, _ = H5SaverLowLevel.open_for_reading(path, force_swmr=True)
            try:
                abs_path = f'{self._h5_base}/{actual_rel}'.replace('//', '/')
                ds = self._load_dwa_from_node(h5saver, abs_path)
                if ds is None:
                    return None
                self._h5_snapshot[actual_rel] = ds
                if actual_rel != rel_path:
                    self._h5_snapshot[rel_path] = ds
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

        if self._is_swmr_live:
            try:
                from pymodaq_data.h5modules.swmr import refresh_datasets
                refresh_datasets(self._h5saver_live.h5file)
            except Exception as exc:
                logger.debug(f'SWMR refresh failed: {exc}')

        progress = self._read_scan_progress(self._h5saver_live)
        if progress is not None and progress == self._scan_progress:
            return
        self._scan_progress = progress

        changed: set = set()
        for rel_path in effective_watched:
            ds = self._load_dataset_live(self._h5saver_live, rel_path)
            if ds is not None:
                self._h5_snapshot[rel_path] = ds
                changed.add(rel_path)

        if changed:
            self._eval_formulas(changed)
            self._set_status(f'Synced {time.strftime("%H:%M:%S")}')

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
        actual_rel = self._resolve_scan_alias(rel_path)
        abs_path = f'{self._h5_base}/{actual_rel}'.replace('//', '/')
        try:
            return self._load_dwa_from_node(h5saver, abs_path)
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

        for formula in self._formula_for.values():
            try:
                for name in extract_data_names(formula):
                    is_h5 = name in self._h5_meta or (
                        name.startswith('Scan/') and
                        self._active_scan_prefix is not None)
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
            if deps and not (deps & changed):
                continue

            try:
                formula_eval, _ = replace_names_in_formula_xr(
                    formula, computed_names=computed_names,
                )
                result = eval(formula_eval, {'np': np, 'xr': xr, '_xr': xr_ctx})
                dwa = _wrap_result(result, name)

                if isinstance(result, xr.DataArray):
                    ds_result = result.to_dataset(name=name)
                elif isinstance(result, xr.Dataset):
                    ds_result = result
                else:
                    ds_result = dwa.to_xarray()

                self._xr_ctx_computed[name] = ds_result
                self._console.update_computed_live(name, ds_result)
                xr_ctx[name] = ds_result
                changed.add(name)

                self._browser.update_computed_info(name, ds_result)
                if name in self._display_names:
                    self._viewer_widget.update(name, dwa)

            except Exception as exc:
                self._set_status(f'Formula "{name}": {exc}', error=True)

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


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = QMainWindow()
    area = DockArea()
    win.setCentralWidget(area)
    win.resize(1280, 800)
    win.setWindowTitle('DataMixer GUI')
    h5_path = sys.argv[1] if len(sys.argv) > 1 else ''
    w = DataMixerGUI(area, dashboard=None)
    if h5_path:
        w.settings.child('h5_path').setValue(h5_path)
        w._load_keys()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
