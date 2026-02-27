"""Top-level DataMixer GUI composition.

Usage
-----
    python -m pymodaq.extensions.data_mixer.gui.data_mixer_gui [path/to/scan.h5]
    # or:
    from pymodaq.extensions.data_mixer.gui.data_mixer_gui import DataMixerGUI, main
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QSplitter, QFileDialog,
)

from pymodaq_data.h5modules.data_saving import DataLoader
from pymodaq_data.h5modules.saving import H5SaverLowLevel
from pymodaq_data.h5modules.backends import backends_available

from pymodaq.extensions.data_mixer.gui.variable_browser import VariableBrowserWidget
from pymodaq.extensions.data_mixer.gui.info_panel import InfoPanelWidget
from pymodaq.extensions.data_mixer.gui.console import FormulaConsole, _QTCONSOLE


class DataMixerGUI(QWidget):
    """Main DataMixer GUI widget.

    Layout
    ------
    QVBoxLayout
      ├── file_row: [Browse] [path QLineEdit] [Load] [mode badge]
      └── QSplitter(Horizontal)
           ├── left_panel  QSplitter(Vertical, ~320 px)
           │    ├── VariableBrowserWidget    (stretch 3)
           │    └── InfoPanelWidget          (stretch 2)
           └── right_panel
                └── FormulaConsole           (stretch 1)
    """

    def __init__(self, h5_path: str = '', parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._xr_ctx_h5: dict = {}         # name → xr.Dataset (H5 data)
        self._xr_ctx_computed: dict = {}   # name → xr.Dataset (computed)
        self._connected: dict[str, bool] = {}  # var_name → is connected to live scan
        self._formula_for: dict[str, str] = {}  # var_name → formula text

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
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText('Path to .h5 file …')
        load_btn = QPushButton('Load')
        load_btn.clicked.connect(self._load_keys)

        mode_text = 'IPython + Editor ✓' if _QTCONSOLE else 'text editor'
        mode_label = QLabel(f'[{mode_text}]')
        mode_label.setStyleSheet(
            'color: #1a6b1a; font-weight: bold;' if _QTCONSOLE
            else 'color: #888;')

        file_row.addWidget(browse_btn)
        file_row.addWidget(self._path_edit, stretch=1)
        file_row.addWidget(load_btn)
        file_row.addWidget(mode_label)
        root.addLayout(file_row)

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

        root.addWidget(h_splitter)

        # Signal wiring
        self._browser.item_selected_sig.connect(self._on_item_selected)
        self._browser.insert_ref_sig.connect(self._console.insert_at_cursor)
        self._browser.delete_computed_sig.connect(self._on_delete_computed)
        self._browser.connect_to_scan_sig.connect(self._on_connect_scan)
        self._console.variable_stored_sig.connect(self._on_new_variable)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open H5 file', '',
            'HDF5 files (*.h5 *.hdf5 *.hdf);;All files (*)')
        if path:
            self._path_edit.setText(path)
            self._load_keys()

    def _on_item_selected(self, ds_name: str, var_name: str) -> None:
        """Display info for the selected item."""
        # Look in H5 context first, then computed
        ds = self._xr_ctx_h5.get(ds_name) or self._xr_ctx_computed.get(ds_name)
        if ds is None:
            return
        source = 'Computed' if ds_name in self._xr_ctx_computed else 'H5'
        formula = self._formula_for.get(ds_name)
        self._info_panel.display(ds_name, ds, source=source,
                                 formula=formula, var_name=var_name)

    def _on_delete_computed(self, name: str) -> None:
        self._xr_ctx_computed.pop(name, None)
        self._formula_for.pop(name, None)
        self._connected.pop(name, None)
        self._browser.remove_computed(name)

    def _on_connect_scan(self, name: str, flag: bool) -> None:
        """Store live-scan connection state (consumed by future timer logic)."""
        self._connected[name] = flag

    def _on_new_variable(self, name: str, ds, formula: str) -> None:
        """A computed variable was stored in the console — add to browser."""
        self._xr_ctx_computed[name] = ds
        self._formula_for[name] = formula
        self._browser.add_computed(name, ds)

    # ── H5 loading ────────────────────────────────────────────────────────────

    def _load_keys(self) -> None:
        path = Path(self._path_edit.text().strip())
        if not path.is_file():
            return

        errors = {}
        for backend in [b for b in ('tables', 'h5py') if b in backends_available]:
            h5saver = H5SaverLowLevel(backend=backend)
            try:
                h5saver.init_file(file_name=path, new_file=False)
                loader = DataLoader(h5saver)
                dte = loader.load_all('/')
                h5saver.close_file()

                names = dte.get_full_names()

                # Build xarray context
                xr_ctx_h5: dict = {}
                try:
                    for full_name in names:
                        dwa = dte.get_data_from_full_name(full_name)
                        xr_ctx_h5[full_name] = dwa.to_xarray()
                except Exception:
                    xr_ctx_h5 = {}

                self._xr_ctx_h5 = xr_ctx_h5
                self._browser.load_h5(xr_ctx_h5)
                self._console.push_h5_context(xr_ctx_h5)
                self._info_panel.clear()
                return

            except Exception as exc:
                errors[backend] = exc
                try:
                    h5saver.close_file()
                except Exception:
                    pass

    # ── public API ────────────────────────────────────────────────────────────

    def get_connected_names(self) -> list[str]:
        """Return variable names currently connected to live scan."""
        return [name for name, flag in self._connected.items() if flag]


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    h5_path = sys.argv[1] if len(sys.argv) > 1 else ''
    w = DataMixerGUI(h5_path)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
