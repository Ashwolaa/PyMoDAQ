"""Small GUI for testing H5 formulas interactively.

Usage:
    python formula_debugger.py
    python formula_debugger.py path/to/scan.h5   # pre-load a file

Autocomplete: type  {  inside the formula editor to get a popup of all
available H5 keys and previously defined variable names.

Supported formula syntax:
    {key}              DataWithAxes  — arithmetic works directly (+  -  *  /)
    {key}.data[0]      numpy array   — use for np.gradient, np.convolve, etc.
                       (result is automatically wrapped back to DataWithAxes)
    name = expr        names the output; bare expr gets an auto-name
    # comment          ignored
"""
import sys
from pathlib import Path

import numpy as np
from qtpy import QtCore
from qtpy.QtCore import Qt
from qtpy.QtGui import QFont, QTextCursor
from qtpy.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QListWidget, QPlainTextEdit,
    QTextEdit, QLabel, QSplitter, QFileDialog, QAbstractItemView,
)

from pymodaq_data.data import DataToExport, DataWithAxes, DataSource
from pymodaq_data.h5modules.saving import H5SaverLowLevel
from pymodaq_data.h5modules.data_saving import DataLoader
from pymodaq_data.h5modules.backends import backends_available

from pymodaq.extensions.data_mixer.parser import (
    parse_named_formulae,
    replace_names_in_formula,
)


# ── DTE that handles plain (no-slash) names for formula results ───────────────

def _wrap_result(result, name: str) -> DataWithAxes:
    """Coerce any eval() return value to a named DataWithAxes.

    DataWithAxes           → rename and return
    np.ndarray             → wrap as single-array DataWithAxes
    tuple/list of ndarray  → np.gradient returns one array per axis; each is
                             stored as a separate entry in .data so
                             {name}.data[0] = axis-0, {name}.data[1] = axis-1
    scalar                 → wrap as 1-element array
    """
    if isinstance(result, DataWithAxes):
        result.name = name
        return result
    if isinstance(result, np.ndarray):
        return DataWithAxes(name, source=DataSource['calculated'], data=[result])
    if isinstance(result, (tuple, list)) and all(isinstance(r, np.ndarray) for r in result):
        return DataWithAxes(name, source=DataSource['calculated'], data=list(result))
    if isinstance(result, (int, float, np.integer, np.floating, np.bool_)):
        return DataWithAxes(name, source=DataSource['calculated'],
                            data=[np.array([float(result)])])
    raise TypeError(
        f'Formula returned {type(result).__name__!r} — expected a DataWithAxes, '
        f'numpy array, tuple of arrays, or scalar.')


class FormulaDTE(DataToExport):
    """DataToExport whose get_data_from_full_name also accepts bare names.

    The base implementation always does ``full_name.split('/')[1]``, which
    crashes on a name like ``'a'`` (no slash).  Formula results are stored
    with plain names, so we add a fallback that searches by ``.name`` directly.
    """
    def get_data_from_full_name(self, full_name: str, deepcopy: bool = False):
        if '/' in full_name:
            return super().get_data_from_full_name(full_name, deepcopy)
        matches = [dwa for dwa in self.data if dwa.name == full_name]
        if not matches:
            raise KeyError(f'No data named {full_name!r}')
        dwa = matches[0]
        return dwa.deepcopy() if deepcopy else dwa


# ── Formula editor with { } autocomplete ─────────────────────────────────────

class FormulaEditor(QPlainTextEdit):
    """QPlainTextEdit that shows a completion popup whenever the cursor is
    inside an unclosed ``{``.  Double-clicking or pressing Enter/Tab in the
    popup inserts the selection and closes the brace."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._completions: list[str] = []

        self._popup = QListWidget(self)
        self._popup.setWindowFlags(Qt.ToolTip)
        self._popup.setFocusPolicy(Qt.NoFocus)
        self._popup.setFocusProxy(self)
        self._popup.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._popup.itemClicked.connect(self._do_complete)
        self._popup.hide()

    # ── public API ──────────────────────────────────────────────────────────

    def set_completions(self, words: list[str]) -> None:
        self._completions = sorted(set(words))
        self._update_popup()

    def add_completions(self, words: list[str]) -> None:
        self._completions = sorted(set(self._completions) | set(words))
        self._update_popup()

    # ── internal ────────────────────────────────────────────────────────────

    def _brace_prefix(self) -> str | None:
        """Text typed after the last unclosed '{', or None if not in context."""
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        brace = text.rfind('{', 0, pos)
        if brace < 0:
            return None
        if text.find('}', brace, pos) >= 0:
            return None          # brace already closed
        return text[brace + 1: pos]

    def _update_popup(self) -> None:
        prefix = self._brace_prefix()
        if prefix is None:
            self._popup.hide()
            return
        matches = [c for c in self._completions if prefix.lower() in c.lower()]
        if not matches:
            self._popup.hide()
            return
        self._popup.clear()
        for m in matches:
            self._popup.addItem(m)
        self._popup.setCurrentRow(0)
        row_h = self._popup.sizeHintForRow(0) + 2
        self._popup.resize(520, min(len(matches) * row_h + 4, 280))
        self._popup.move(self.mapToGlobal(self.cursorRect().bottomLeft()))
        self._popup.show()

    def _do_complete(self, item) -> None:
        text = item.text()
        cursor = self.textCursor()
        pos = cursor.position()
        full = self.toPlainText()
        brace = full.rfind('{', 0, pos)
        if brace >= 0:
            cursor.setPosition(brace + 1)
            cursor.setPosition(pos, QTextCursor.KeepAnchor)
            cursor.insertText(text + '}')
            self.setTextCursor(cursor)
        self._popup.hide()
        self.setFocus()

    def keyPressEvent(self, event) -> None:
        if self._popup.isVisible():
            key = event.key()
            if key == Qt.Key_Escape:
                self._popup.hide()
                return
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                item = self._popup.currentItem()
                if item:
                    self._do_complete(item)
                return
            if key == Qt.Key_Down:
                self._popup.setCurrentRow(
                    min(self._popup.currentRow() + 1, self._popup.count() - 1))
                return
            if key == Qt.Key_Up:
                self._popup.setCurrentRow(
                    max(self._popup.currentRow() - 1, 0))
                return
        super().keyPressEvent(event)
        self._update_popup()

    def focusOutEvent(self, event) -> None:
        self._popup.hide()
        super().focusOutEvent(event)


# ── Main window ───────────────────────────────────────────────────────────────

class FormulaDebugger(QWidget):

    def __init__(self, h5_path: str = ''):
        super().__init__()
        self._dte_from_h5: DataToExport | None = None
        self._setup_ui()
        if h5_path:
            self.path_edit.setText(h5_path)
            self._load_keys()

    def _setup_ui(self):
        self.setWindowTitle('H5 Formula Debugger')
        self.resize(1150, 720)
        root = QVBoxLayout(self)

        # ── file row ─────────────────────────────────────────────────────────
        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText('Path to .h5 file …')
        browse_btn = QPushButton('Browse')
        browse_btn.clicked.connect(self._browse)
        load_btn = QPushButton('Load Keys')
        load_btn.clicked.connect(self._load_keys)
        file_row.addWidget(self.path_edit, stretch=1)
        file_row.addWidget(browse_btn)
        file_row.addWidget(load_btn)
        root.addLayout(file_row)

        # ── main splitter ────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # left: H5 keys + defined variables
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)

        ll.addWidget(_bold('H5 keys  (double-click to insert):'))
        self.keys_list = QListWidget()
        self.keys_list.itemDoubleClicked.connect(self._insert_item)
        ll.addWidget(self.keys_list, stretch=3)

        ll.addWidget(_bold('Defined variables  (double-click to insert):'))
        self.vars_list = QListWidget()
        self.vars_list.itemDoubleClicked.connect(self._insert_item)
        ll.addWidget(self.vars_list, stretch=2)

        splitter.addWidget(left)

        # right: hint + editor + compute + output
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)

        hint = QLabel(
            '<b>Syntax:</b> &nbsp;'
            '<code>{key}</code> → DataWithAxes &nbsp;·&nbsp;'
            'arithmetic (<code>+ - * /</code>) and scalar math work directly &nbsp;·&nbsp;'
            '<code>{key}.data[0]</code> → raw numpy array '
            '(required for <code>np.max / np.gradient / np.convolve</code> …) &nbsp;·&nbsp;'
            'numpy reductions on <code>.data[0]</code> return a scalar — '
            'use them inline: <code>{a} / np.max({a}.data[0])</code> &nbsp;·&nbsp;'
            'type <code>{</code> to autocomplete'
        )
        hint.setWordWrap(True)
        rl.addWidget(hint)

        rl.addWidget(_bold('Formulas  (one per line,  name = expr  or bare expr):'))
        self.formula_edit = FormulaEditor()
        self.formula_edit.setPlaceholderText(
            '# Arithmetic on DataWithAxes:\n'
            'doubled  = {RawData/Scan000/Detector000/…} * 2\n'
            '\n'
            '# Numpy on raw array (.data[0]) — result is auto-wrapped:\n'
            'gradient = np.gradient({doubled}.data[0])\n'
            'smooth   = np.convolve({doubled}.data[0], np.ones(5)/5, mode="same")\n'
        )
        self.formula_edit.setFont(_mono_font())
        rl.addWidget(self.formula_edit, stretch=2)

        compute_btn = QPushButton('⏵  Compute  (Ctrl+Enter)')
        compute_btn.setFixedHeight(34)
        compute_btn.clicked.connect(self._compute)
        rl.addWidget(compute_btn)

        from qtpy.QtWidgets import QShortcut
        from qtpy.QtGui import QKeySequence
        QShortcut(QKeySequence('Ctrl+Return'), self).activated.connect(self._compute)

        rl.addWidget(_bold('Output:'))
        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setFont(_mono_font())
        rl.addWidget(self.output_edit, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([320, 830])
        root.addWidget(splitter)

    # ── slots ────────────────────────────────────────────────────────────────

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open H5 file', '', 'HDF5 files (*.h5 *.hdf5 *.hdf);;All files (*)')
        if path:
            self.path_edit.setText(path)
            self._load_keys()

    def _insert_item(self, item):
        self.formula_edit.insertPlainText(f'{{{item.text()}}}')
        self.formula_edit.setFocus()

    def _load_keys(self):
        import traceback
        path = Path(self.path_edit.text().strip())
        if not path.is_file():
            self._log('<span style="color:red">ERROR: file not found</span>')
            return

        tried = {}
        for backend in [b for b in ('tables', 'h5py') if b in backends_available]:
            h5saver = H5SaverLowLevel(backend=backend)
            try:
                h5saver.init_file(file_name=path, new_file=False)
                self._dte_from_h5 = DataLoader(h5saver).load_all('/')
                h5saver.close_file()
                names = self._dte_from_h5.get_full_names()
                self.keys_list.clear()
                for n in names:
                    self.keys_list.addItem(n)
                self.vars_list.clear()
                self.formula_edit.set_completions(names)
                self._log(
                    f'<span style="color:green"><b>Loaded</b> {len(names)} key(s) '
                    f'via {backend}</span><br>'
                    + ''.join(f'&nbsp;&nbsp;{n}<br>' for n in names)
                )
                return
            except Exception as exc:
                tried[backend] = traceback.format_exc()
                try:
                    h5saver.close_file()
                except Exception:
                    pass

        self._log('<span style="color:red"><b>All backends failed.</b></span>')
        for backend, tb in tried.items():
            self._log(f'<b>{backend}:</b><br><pre>{tb}</pre>')

    def _compute(self):
        if self._dte_from_h5 is None:
            self._log('<span style="color:red">Load an H5 file first.</span>')
            return

        formula_text = self.formula_edit.toPlainText()
        formulae = parse_named_formulae(formula_text)
        if not formulae:
            self._log('No formulas to evaluate.')
            return

        self._log(f'<b>── Computing {len(formulae)} formula(s) ──</b>')

        # FormulaDTE: same as DataToExport but get_data_from_full_name also
        # accepts plain names like 'a' (no origin/name slash required).
        dte = FormulaDTE('Combined')
        for dwa in self._dte_from_h5.data:
            dte.append(dwa)

        defined_this_run: list[str] = []

        for out_name, expr in formulae:
            formula_to_eval, _ = replace_names_in_formula(expr)
            self._log(f'<b>[{out_name}]</b> &nbsp; <code>{expr}</code>')
            try:
                result = eval(formula_to_eval)   # np and dte are in scope
                result = _wrap_result(result, out_name)
                dte.append(result)
                defined_this_run.append(out_name)
                summary = '  '.join(
                    f'data[{i}] shape={arr.shape} '
                    f'min={float(arr.min()):.4g} max={float(arr.max()):.4g}'
                    for i, arr in enumerate(result.data)
                )
                self._log(
                    f'&nbsp;&nbsp;<span style="color:green">OK</span> &nbsp;{summary}')
            except Exception as exc:
                hint = ''
                msg = str(exc)
                if 'list index out of range' in msg or '__array_function__' in msg:
                    hint = (
                        '<br>&nbsp;&nbsp;<i>Hint: numpy reduction functions '
                        '(<code>np.max</code>, <code>np.sum</code> …) do not work '
                        'directly on DataWithAxes — use <code>{key}.data[0]</code> '
                        'to get the raw array first: '
                        '<code>{a} / np.max({a}.data[0])</code></i>'
                    )
                self._log(
                    f'&nbsp;&nbsp;<span style="color:red">ERROR: {exc}</span>{hint}')

        # update variable panel and autocomplete with this run's outputs
        current_vars = [self.vars_list.item(i).text()
                        for i in range(self.vars_list.count())]
        for name in defined_this_run:
            if name not in current_vars:
                self.vars_list.addItem(name)
        self.formula_edit.add_completions(defined_this_run)
        self._log('<hr>')

    def _log(self, html: str):
        self.output_edit.append(html)


# ── helpers ───────────────────────────────────────────────────────────────────

def _mono_font() -> QFont:
    f = QFont('Courier New')
    f.setPointSize(10)
    return f


def _bold(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setTextFormat(Qt.RichText)
    return lbl


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    h5_path = sys.argv[1] if len(sys.argv) > 1 else ''
    w = FormulaDebugger(h5_path)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
