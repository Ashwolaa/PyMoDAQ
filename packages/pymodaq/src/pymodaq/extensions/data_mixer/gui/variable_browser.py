"""Variable browser widget for the DataMixer GUI.

Shows H5 datasets and computed results in a two-section tree.  Double-clicking
a node inserts a ``{name}`` reference into the formula console.
"""
from __future__ import annotations

from typing import Optional

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QAbstractItemView, QMenu, QAction,
)
from qtpy.QtGui import QFont


class VariableBrowserWidget(QWidget):
    """Tree widget showing H5 datasets (read-only) and computed variables.

    Signals
    -------
    item_selected_sig(ds_name, var_name)
        Emitted when a node is single-clicked.  *var_name* is empty for
        dataset-level nodes; non-empty for leaf (channel) nodes.
    insert_ref_sig(text)
        Text fragment ready to insert at the console cursor.
    delete_computed_sig(name)
        User asked to delete the named computed variable.
    connect_to_scan_sig(name, connected)
        User toggled the "connect to live scan" checkbox for a computed var.
    """

    item_selected_sig = Signal(str, str)   # (ds_name, var_name)
    insert_ref_sig = Signal(str)           # text to insert at cursor
    delete_computed_sig = Signal(str)      # name to remove
    connect_to_scan_sig = Signal(str, bool)  # (var_name, connected)

    # Tree column indices
    _COL_NAME = 0
    _COL_INFO = 1
    _COL_CONN = 2   # connect-to-scan checkbox column (Computed rows only)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._h5_names: list[str] = []
        self._computed: dict[str, object] = {}   # name → xr.Dataset
        self._setup_ui()

    # ── setup ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Search box
        self._search = QLineEdit()
        self._search.setPlaceholderText('Filter variables…')
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(['Name', 'Info', '⟳'])
        self._tree.header().setStretchLastSection(False)
        self._tree.header().resizeSection(self._COL_NAME, 200)
        self._tree.header().resizeSection(self._COL_INFO, 160)
        self._tree.header().resizeSection(self._COL_CONN, 24)
        self._tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemClicked.connect(self._on_single_click)
        layout.addWidget(self._tree)

        # Top-level section headers
        bold = QFont()
        bold.setBold(True)

        self._h5_root = QTreeWidgetItem(self._tree, ['H5 Data', '', ''])
        self._h5_root.setFont(self._COL_NAME, bold)
        self._h5_root.setFlags(self._h5_root.flags() & ~Qt.ItemIsSelectable)

        self._comp_root = QTreeWidgetItem(self._tree, ['Computed', '', ''])
        self._comp_root.setFont(self._COL_NAME, bold)
        self._comp_root.setFlags(self._comp_root.flags() & ~Qt.ItemIsSelectable)

        self._tree.expandAll()

    # ── public API ────────────────────────────────────────────────────────────

    def load_h5(self, xr_ctx_h5: dict):
        """Populate the H5 Data section from a name→xr.Dataset mapping."""
        # Remove old H5 children
        while self._h5_root.childCount():
            self._h5_root.removeChild(self._h5_root.child(0))
        self._h5_names = []

        for full_name, ds in xr_ctx_h5.items():
            self._h5_names.append(full_name)
            info = self._ds_info(ds)
            ds_item = QTreeWidgetItem(self._h5_root, [full_name, info, ''])
            ds_item.setData(self._COL_NAME, Qt.UserRole, ('h5_ds', full_name))
            ds_item.setToolTip(self._COL_NAME, full_name)

            # Add one leaf per data variable
            for var_name, var in ds.data_vars.items():
                dims = ', '.join(str(d) for d in var.dims)
                leaf_info = f'{var.dtype} ({dims})'
                leaf = QTreeWidgetItem(ds_item, [var_name, leaf_info, ''])
                leaf.setData(self._COL_NAME, Qt.UserRole, ('h5_var', full_name, var_name))

        self._h5_root.setExpanded(True)
        self._apply_filter(self._search.text())

    def add_computed(self, name: str, ds):
        """Add or update a computed variable node."""
        self._computed[name] = ds

        # Update existing item if present
        for i in range(self._comp_root.childCount()):
            item = self._comp_root.child(i)
            if item.text(self._COL_NAME) == name:
                item.setText(self._COL_INFO, self._ds_info(ds))
                return

        # Create new item
        info = self._ds_info(ds)
        item = QTreeWidgetItem(self._comp_root, [name, info, ''])
        item.setData(self._COL_NAME, Qt.UserRole, ('computed', name))
        item.setToolTip(self._COL_NAME, name)
        item.setCheckState(self._COL_CONN, Qt.Unchecked)
        self._comp_root.setExpanded(True)
        self._apply_filter(self._search.text())

    def remove_computed(self, name: str):
        """Remove a computed variable by name."""
        self._computed.pop(name, None)
        for i in range(self._comp_root.childCount()):
            item = self._comp_root.child(i)
            if item.text(self._COL_NAME) == name:
                self._comp_root.removeChild(item)
                return

    def clear_computed(self):
        """Reset the Computed section."""
        self._computed.clear()
        while self._comp_root.childCount():
            self._comp_root.removeChild(self._comp_root.child(0))

    def set_filter(self, text: str):
        """Show only items whose name contains *text* (case-insensitive)."""
        self._search.setText(text)

    # ── internal slots ────────────────────────────────────────────────────────

    def _apply_filter(self, text: str):
        text = text.lower()
        for section in (self._h5_root, self._comp_root):
            for i in range(section.childCount()):
                item = section.child(i)
                visible = (not text) or (text in item.text(self._COL_NAME).lower())
                item.setHidden(not visible)
                # For H5 dataset nodes, also filter their children
                for j in range(item.childCount()):
                    child = item.child(j)
                    child_visible = (not text) or (
                        text in item.text(self._COL_NAME).lower() or
                        text in child.text(self._COL_NAME).lower()
                    )
                    child.setHidden(not child_visible)

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
            if column == self._COL_CONN:
                # Checkbox toggle
                checked = item.checkState(self._COL_CONN) == Qt.Checked
                self.connect_to_scan_sig.emit(name, checked)
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
        item = self._tree.itemAt(pos)
        if item is None:
            return
        data = item.data(self._COL_NAME, Qt.UserRole)
        if data is None or data[0] != 'computed':
            return
        name = data[1]
        menu = QMenu(self)
        delete_action = QAction('Delete variable', self)
        delete_action.triggered.connect(lambda: self.delete_computed_sig.emit(name))
        menu.addAction(delete_action)
        menu.exec_(self._tree.viewport().mapToGlobal(pos))

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
        except Exception:
            return ''

