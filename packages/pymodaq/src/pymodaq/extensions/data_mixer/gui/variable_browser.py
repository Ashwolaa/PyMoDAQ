"""Variable browser widget for the DataMixer GUI.

Shows H5 datasets (top pane) and computed results (bottom pane) in two
independent tree widgets separated by a vertical splitter so that computed
variables remain visible regardless of how many H5 datasets are loaded.
Double-clicking a node inserts a ``{name}`` reference into the formula console.
"""
from __future__ import annotations

from typing import Optional

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem,
    QLineEdit, QAbstractItemView,
    QMenu, QAction, QPushButton, QSplitter,
)
from qtpy.QtGui import QFont

from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))

from pymodaq_gui.utils.styling import create_icon


class VariableBrowserWidget(QWidget):
    """Two-pane tree: H5 datasets (top) and computed variables (bottom).

    Signals
    -------
    item_selected_sig(ds_name, var_name)
        Emitted when a node is single-clicked.  *var_name* is empty for
        dataset-level nodes; non-empty for leaf (channel) nodes.
    insert_ref_sig(text)
        Text fragment ready to insert at the console cursor.
    delete_computed_sig(name)
        User asked to delete the named computed variable.
    show_var_sig(name, display)
        User toggled the Display checkbox on a computed variable row.
    send_formula_sig(name)
        Recall the formula for *name* in the formula editor.
    recompute_all_sig()
        Request recompute of all stored formulas.
    clear_all_computed_sig()
        Request full clear of computed vars.
    load_and_show_h5_sig(name)
        User requested to load and display an H5 dataset in the viewer window.
    """

    item_selected_sig      = Signal(str, str)
    insert_ref_sig         = Signal(str)
    delete_computed_sig    = Signal(str)
    show_var_sig           = Signal(str, bool)
    send_formula_sig       = Signal(str)
    recompute_all_sig      = Signal()
    clear_all_computed_sig = Signal()
    load_and_show_h5_sig   = Signal(str)

    # Tree column indices
    _COL_NAME = 0
    _COL_INFO = 1
    _COL_DISP = 2   # Display-in-viewer checkbox (Computed rows only)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._h5_names: list[str] = []
        self._setup_ui()

    # ── setup ─────────────────────────────────────────────────────────────────

    def _make_tree(self, header_label: str) -> tuple[QTreeWidget, QTreeWidgetItem]:
        """Create a QTreeWidget with 3 standard columns and a bold root item."""
        tree = QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels([header_label, 'Info', '👁'])
        tree.header().setStretchLastSection(False)
        tree.header().resizeSection(self._COL_NAME, 200)
        tree.header().resizeSection(self._COL_INFO, 160)
        tree.header().resizeSection(self._COL_DISP,  24)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_context_menu)
        tree.itemDoubleClicked.connect(self._on_double_click)
        tree.itemClicked.connect(self._on_single_click)

        bold = QFont()
        bold.setBold(True)
        root = QTreeWidgetItem(tree, [header_label, '', ''])
        root.setFont(self._COL_NAME, bold)
        root.setFlags(root.flags() & ~Qt.ItemIsSelectable)
        root.setExpanded(True)
        return tree, root

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Shared filter box — applies to both trees
        self._search = QLineEdit()
        self._search.setPlaceholderText('Filter variables…')
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        # Two independent trees in a vertical splitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        self._h5_tree, self._h5_root = self._make_tree('H5 Data')
        self._h5_tree.setToolTip('Double-click to insert {reference} at cursor')

        self._comp_tree, self._comp_root = self._make_tree('Computed')
        self._comp_tree.setToolTip('👁 = display in viewer window')

        splitter.addWidget(self._h5_tree)
        splitter.addWidget(self._comp_tree)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Mini-toolbar at bottom
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 2, 0, 0)

        recompute_btn = QPushButton('Recompute all')
        recompute_btn.setFlat(True)
        recompute_btn.setToolTip(
            'Re-run all previously stored formulas with current H5 data.\n'
            'A validation pass is shown in the output panel first.')
        recompute_btn.clicked.connect(self.recompute_all_sig.emit)
        recompute_btn.setIcon(create_icon('repeat'))
        bottom_row.addWidget(recompute_btn)

        clear_btn = QPushButton('Clear computed')
        clear_btn.setFlat(True)
        clear_btn.setToolTip('Clear all computed variables from browser and console')
        clear_btn.clicked.connect(self.clear_all_computed_sig.emit)
        clear_btn.setIcon(create_icon('ink_eraser'))
        bottom_row.addWidget(clear_btn)

        layout.addLayout(bottom_row)

    # ── public API ────────────────────────────────────────────────────────────

    def load_h5(self, xr_ctx_h5: dict, info: dict = None):
        """Populate the H5 Data section from a name→xr.Dataset mapping.

        Parameters
        ----------
        xr_ctx_h5:
            ``{rel_path: xr.Dataset | None}`` mapping.  Values may be ``None``
            when names-only mode is used (data loaded lazily on demand).
        info:
            Optional ``{rel_path: str}`` from :func:`_collect_h5_names_and_info`.
            When present the Info column is filled immediately without loading
            any array data.  Falls back to ``_ds_info(ds)`` when absent.
        """
        while self._h5_root.childCount():
            self._h5_root.removeChild(self._h5_root.child(0))
        self._h5_names = []

        # Group by origin (first path component, e.g. 'Scan000')
        scan_groups: dict = {}
        for full_name, ds in xr_ctx_h5.items():
            origin, _, _ = full_name.partition('/')
            scan_groups.setdefault(origin, []).append((full_name, ds))

        multi_scan = len(scan_groups) > 1
        italic_font = QFont()
        italic_font.setItalic(True)

        for origin, items in scan_groups.items():
            if multi_scan:
                scan_item = QTreeWidgetItem(self._h5_root, [origin, '', '', ''])
                scan_item.setFont(self._COL_NAME, italic_font)
                scan_item.setFlags(scan_item.flags() & ~Qt.ItemIsSelectable)
                scan_item.setExpanded(True)
                parent = scan_item
            else:
                parent = self._h5_root

            for full_name, ds in items:
                self._h5_names.append(full_name)
                display = full_name.split('/', 1)[-1] if multi_scan else full_name
                if info is not None:
                    info_str = info.get(full_name, '—')
                elif ds is not None:
                    info_str = self._ds_info(ds)
                else:
                    info_str = '—'
                ds_item = QTreeWidgetItem(parent, [display, info_str, ''])
                ds_item.setData(self._COL_NAME, Qt.UserRole, ('h5_ds', full_name))
                ds_item.setToolTip(self._COL_NAME, full_name)

                if ds is not None:
                    try:
                        for var_name, var in ds.data_vars.items():
                            dims = ', '.join(str(d) for d in var.dims)
                            leaf_info = f'{var.dtype} ({dims})'
                            leaf = QTreeWidgetItem(ds_item, [var_name, leaf_info, ''])
                            leaf.setData(self._COL_NAME, Qt.UserRole,
                                         ('h5_var', full_name, var_name))
                    except Exception as exc:
                        logger.debug(f'Cannot build leaf nodes for {full_name!r}: {exc}')

        self._h5_root.setExpanded(True)
        self._apply_filter(self._search.text())

    def add_computed(self, name: str, ds):
        """Add or update a computed variable node."""
        for i in range(self._comp_root.childCount()):
            item = self._comp_root.child(i)
            if item.text(self._COL_NAME) == name:
                item.setText(self._COL_INFO, self._ds_info(ds))
                return

        info = self._ds_info(ds)
        item = QTreeWidgetItem(self._comp_root, [name, info, ''])
        item.setData(self._COL_NAME, Qt.UserRole, ('computed', name))
        item.setToolTip(self._COL_NAME, name)
        item.setToolTip(self._COL_DISP, 'Display in viewer window')
        item.setCheckState(self._COL_DISP, Qt.Unchecked)
        self._comp_root.setExpanded(True)
        self._apply_filter(self._search.text())

    def remove_computed(self, name: str):
        """Remove a computed variable by name."""
        for i in range(self._comp_root.childCount()):
            item = self._comp_root.child(i)
            if item.text(self._COL_NAME) == name:
                self._comp_root.removeChild(item)
                return

    def clear_computed(self):
        """Reset the Computed section."""
        while self._comp_root.childCount():
            self._comp_root.removeChild(self._comp_root.child(0))

    def set_filter(self, text: str):
        """Show only items whose name contains *text* (case-insensitive)."""
        self._search.setText(text)

    def _iter_h5_ds_items(self):
        """Yield every ``h5_ds`` QTreeWidgetItem, regardless of nesting depth."""
        for i in range(self._h5_root.childCount()):
            item = self._h5_root.child(i)
            data = item.data(self._COL_NAME, Qt.UserRole)
            if data and data[0] == 'h5_ds':
                yield item
            else:
                for j in range(item.childCount()):
                    child = item.child(j)
                    cdata = child.data(self._COL_NAME, Qt.UserRole)
                    if cdata and cdata[0] == 'h5_ds':
                        yield child

    def get_display_names(self) -> list[str]:
        """Return names of computed variables whose Display checkbox is checked."""
        displayed = []
        for i in range(self._comp_root.childCount()):
            item = self._comp_root.child(i)
            if item.checkState(self._COL_DISP) == Qt.Checked:
                data = item.data(self._COL_NAME, Qt.UserRole)
                if data and data[0] == 'computed':
                    displayed.append(data[1])
        return displayed

    def update_computed_info(self, name: str, ds) -> None:
        """Refresh the Info column for an existing computed variable row."""
        for i in range(self._comp_root.childCount()):
            item = self._comp_root.child(i)
            if item.text(self._COL_NAME) == name:
                item.setText(self._COL_INFO, self._ds_info(ds))
                return

    def update_h5_info(self, name: str, ds) -> None:
        """Populate Info column (and child variable nodes) for an H5 row.

        Called lazily after *ds* has been loaded on demand.
        """
        if ds is None:
            return
        for item in self._iter_h5_ds_items():
            data = item.data(self._COL_NAME, Qt.UserRole)
            if data and data[0] == 'h5_ds' and data[1] == name:
                item.setText(self._COL_INFO, self._ds_info(ds))
                if item.childCount() == 0:
                    try:
                        for var_name, var in ds.data_vars.items():
                            dims = ', '.join(str(d) for d in var.dims)
                            leaf_info = f'{var.dtype} ({dims})'
                            leaf = QTreeWidgetItem(item, [var_name, leaf_info, ''])
                            leaf.setData(self._COL_NAME, Qt.UserRole,
                                         ('h5_var', name, var_name))
                    except Exception as exc:
                        logger.debug(f'Cannot build leaf nodes for {name!r}: {exc}')
                return

    def uncheck_display(self, name: str) -> None:
        """Uncheck the Display checkbox for *name* (e.g. when a viewer tab is closed)."""
        for i in range(self._comp_root.childCount()):
            item = self._comp_root.child(i)
            if item.text(self._COL_NAME) == name:
                item.setCheckState(self._COL_DISP, Qt.Unchecked)
                return

    # ── internal slots ────────────────────────────────────────────────────────

    def _apply_filter(self, text: str):
        text = text.lower()

        # ── H5 tree ──────────────────────────────────────────────────────────
        for i in range(self._h5_root.childCount()):
            item = self._h5_root.child(i)
            data = item.data(self._COL_NAME, Qt.UserRole)
            if data and data[0] == 'h5_ds':
                # Flat / single-scan mode
                name_match = (not text) or (text in item.text(self._COL_NAME).lower())
                item.setHidden(not name_match)
                for j in range(item.childCount()):
                    child = item.child(j)
                    child.setHidden(not (name_match or (
                        text and text in child.text(self._COL_NAME).lower())))
            else:
                # Multi-scan: item is a scan sub-header
                any_visible = False
                for j in range(item.childCount()):
                    ds_item = item.child(j)
                    ds_name = ds_item.text(self._COL_NAME).lower()
                    scan_name = item.text(self._COL_NAME).lower()
                    ds_match = (not text) or (text in ds_name) or (text in scan_name)
                    ds_item.setHidden(not ds_match)
                    if ds_match:
                        any_visible = True
                    for k in range(ds_item.childCount()):
                        leaf = ds_item.child(k)
                        leaf.setHidden(not (ds_match or (
                            text and text in leaf.text(self._COL_NAME).lower())))
                item.setHidden(not any_visible)

        # ── Computed tree ─────────────────────────────────────────────────────
        for i in range(self._comp_root.childCount()):
            item = self._comp_root.child(i)
            visible = (not text) or (text in item.text(self._COL_NAME).lower())
            item.setHidden(not visible)

    def _on_single_click(self, item: QTreeWidgetItem, column: int):
        data = item.data(self._COL_NAME, Qt.UserRole)
        if data is None:
            return

        kind = data[0]
        if kind == 'h5_ds':
            _, ds_name = data
            self.item_selected_sig.emit(ds_name, '')
        elif kind == 'h5_var':
            _, ds_name, var_name = data
            self.item_selected_sig.emit(ds_name, var_name)
        elif kind == 'computed':
            _, name = data
            if column == self._COL_DISP:
                checked = item.checkState(self._COL_DISP) == Qt.Checked
                self.show_var_sig.emit(name, checked)
            else:
                self.item_selected_sig.emit(name, '')

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        data = item.data(self._COL_NAME, Qt.UserRole)
        if data is None:
            return

        kind = data[0]
        if kind == 'h5_ds':
            _, ds_name = data
            self.insert_ref_sig.emit(f'{{{ds_name}}}')
        elif kind == 'h5_var':
            _, ds_name, var_name = data
            self.insert_ref_sig.emit(f'{{{ds_name}}}["{var_name}"]')
        elif kind == 'computed':
            _, name = data
            self.insert_ref_sig.emit(f'{{{name}}}')

    def _on_context_menu(self, pos):
        tree = self.sender()
        item = tree.itemAt(pos)
        if item is None:
            return
        data = item.data(self._COL_NAME, Qt.UserRole)
        if data is None:
            return

        kind = data[0]
        menu = QMenu(self)

        if kind in ('h5_ds', 'h5_var'):
            if kind == 'h5_ds':
                _, ds_name = data
                ref_text = f'{{{ds_name}}}'
            else:
                _, ds_name, var_name = data
                ref_text = f'{{{ds_name}}}["{var_name}"]'

            copy_action = QAction('Copy reference', self)
            copy_action.setToolTip(f'Copy  {ref_text}  to clipboard')
            copy_action.triggered.connect(
                lambda checked=False, t=ref_text: QApplication.clipboard().setText(t)
            )
            menu.addAction(copy_action)

            insert_action = QAction('Insert reference', self)
            insert_action.setToolTip('Insert reference at formula cursor (same as double-click)')
            insert_action.triggered.connect(
                lambda checked=False, t=ref_text: self.insert_ref_sig.emit(t)
            )
            menu.addAction(insert_action)

            menu.addSeparator()

            show_action = QAction('Open in viewer', self)
            show_action.setToolTip('Load this dataset and display it in the viewer window')
            show_action.triggered.connect(
                lambda checked=False, n=ds_name: self.load_and_show_h5_sig.emit(n)
            )
            menu.addAction(show_action)

        elif kind == 'computed':
            name = data[1]
            send_action = QAction('\u2192 Send formula to editor', self)
            send_action.setToolTip('Append  name = <formula>  to the formula editor')
            send_action.triggered.connect(lambda: self.send_formula_sig.emit(name))
            menu.addAction(send_action)
            menu.addSeparator()
            delete_action = QAction('Delete variable', self)
            delete_action.triggered.connect(lambda: self.delete_computed_sig.emit(name))
            menu.addAction(delete_action)

        else:
            return

        menu.exec_(tree.viewport().mapToGlobal(pos))

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _ds_info(ds) -> str:
        """Short info string for a dataset: dtype and shape of first variable."""
        try:
            if not ds.data_vars:
                return f'{len(ds.data_vars)} vars'
            first_var = next(iter(ds.data_vars.values()))
            shape = tuple(ds.sizes[d] for d in first_var.dims)
            return f'{first_var.dtype} {shape}'
        except Exception as exc:
            logger.debug(f'Cannot format dataset info: {exc}')
            return ''
