"""Small GUI for testing H5 formulas interactively.

Usage:
    python formula_debugger.py
    python formula_debugger.py path/to/scan.h5   # pre-load a file

Formula syntax (xarray path — requires xarray installed):
    {origin/name}              xr.Dataset  (one data-variable per channel)
    {origin/name}["CH00"]      xr.DataArray  — use for math, reductions, slicing
    {origin/name}["CH00"] * 2                element-wise scalar
    {origin/name}["CH00"].mean("time")        reduce over named dim → 2-D DataArray
    {origin/name}["CH00"].isel(time=5)        select one frame → 2-D DataArray
    {a}["a"] + {b}["b"]                       combine two formula results
    np.sqrt({origin/name}["CH00"])            numpy ufunc on DataArray
    np.gradient({origin/name}["CH00"].values) on raw numpy via .values

Named outputs:
    name = expr        stores result as xr.Dataset under 'name', data-var = 'name'
    bare expr          auto-named Formula_NNN

Cross-referencing:
    a = {origin/name}["CH00"].mean("time")
    b = {a}["a"] + 1    ← {a} gives xr.Dataset with var 'a'

type { to autocomplete H5 keys and defined variables.
"""
import html as _html
import sys
from pathlib import Path

import numpy as np
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
    replace_names_in_formula_xr,
)


# ── Result coercion ───────────────────────────────────────────────────────────

def _wrap_result(result, name: str) -> DataWithAxes:
    """Coerce any eval() return value to a named DataWithAxes.

    xr.Dataset  (1 var)  → extract DataArray, convert via from_xarray
    xr.Dataset  (N vars) → from_xarray with attrs dropped
    xr.DataArray         → to_dataset(name=var_name), from_xarray
    DataWithAxes         → rename and return
    np.ndarray           → wrap as single-array DataWithAxes
    tuple/list of arrays → each element as a separate .data entry
    scalar               → wrap as 1-element array
    """
    try:
        import xarray as xr
        if isinstance(result, xr.Dataset):
            if len(result.data_vars) == 1:
                var_name = list(result.data_vars)[0]
                da = result[var_name]
                dwa = DataWithAxes.from_xarray(da.to_dataset(name=var_name))
            else:
                dwa = DataWithAxes.from_xarray(result.drop_attrs())
            dwa.name = name
            return dwa
        if isinstance(result, xr.DataArray):
            var_name = result.name or name
            dwa = DataWithAxes.from_xarray(result.to_dataset(name=var_name))
            dwa.name = name
            return dwa
    except ImportError:
        pass
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
        f'xarray Dataset/DataArray, numpy array, tuple of arrays, or scalar.')


# ── Fallback DTE for when xarray is not installed ────────────────────────────

class FormulaDTE(DataToExport):
    """DataToExport whose get_data_from_full_name also accepts bare names."""
    def get_data_from_full_name(self, full_name: str, deepcopy: bool = False):
        if '/' in full_name:
            return super().get_data_from_full_name(full_name, deepcopy)
        matches = [dwa for dwa in self.data if dwa.name == full_name]
        if not matches:
            raise KeyError(f'No data named {full_name!r}')
        dwa = matches[0]
        return dwa.deepcopy() if deepcopy else dwa


# ── Rich output formatting ────────────────────────────────────────────────────

def _format_xr_html(ds, result_name: str) -> str:
    """HTML summary of an xr.Dataset — similar to IPython's xarray display."""
    _C = 'color:#555'   # label colour
    _B = 'color:#1a3c6b'  # value colour

    rows = []

    # Dimensions
    dims_parts = [f'<b>{d}</b>({n})' for d, n in ds.sizes.items()]
    rows.append(f'<span style="{_C}">Dimensions:</span>  ' + ' &nbsp;·&nbsp; '.join(dims_parts))

    # Coordinates
    for cname, cvar in ds.coords.items():
        units = cvar.attrs.get('units', '')
        units_str = f'  units=<b>{units!r}</b>' if units else ''
        data = cvar.values
        if data.ndim == 1 and data.size > 0:
            rng = f'  [<b>{data[0]:.4g}</b> … <b>{data[-1]:.4g}</b>]'
        elif data.ndim > 1:
            rng = f'  shape={data.shape}'
        else:
            rng = ''
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">*</span> '
            f'<b>{_html.escape(cname)}</b> '
            f'({", ".join(_html.escape(str(d)) for d in cvar.dims)}) '
            f'{cvar.dtype}{rng}{units_str}')

    # Data variables
    for vname, var in ds.data_vars.items():
        vals = var.values
        dims_str = ', '.join(_html.escape(str(d)) for d in var.dims)
        if vals.size > 0:
            stats = (f'  min=<b>{float(vals.min()):.4g}</b>'
                     f'  max=<b>{float(vals.max()):.4g}</b>'
                     f'  mean=<b>{float(vals.mean()):.4g}</b>')
        else:
            stats = '  (empty)'
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">var</span> '
            f'<b>{_html.escape(vname)}</b> '
            f'({dims_str}) {var.dtype}{stats}')

    ref = f'{{<b>{_html.escape(result_name)}</b>}}[&quot;<b>{_html.escape(result_name)}</b>&quot;]'
    header = (f'<span style="color:#1a6b1a"><b>xr.Dataset</b></span>'
              f' — stored in context, reference as {ref}')
    body = '<br>'.join('&nbsp;&nbsp;' + r for r in rows)
    return header + '<br>' + body


def _format_dwa_html(dwa: DataWithAxes) -> str:
    """HTML summary of a DataWithAxes — shape, axes, data stats."""
    _C = 'color:#555'

    rows = []
    rows.append(
        f'shape=<b>{dwa.shape}</b>'
        f'  nav_indexes=<b>{dwa.nav_indexes}</b>'
        f'  distribution=<b>{dwa.distribution.name}</b>'
    )

    for ax in sorted(dwa.axes, key=lambda a: a.index):
        ax_data = ax.get_data()
        units_str = f'  units=<b>{ax.units!r}</b>' if ax.units else ''
        if ax_data is not None and ax_data.size > 0:
            rng = f'  [<b>{ax_data[0]:.4g}</b> … <b>{ax_data[-1]:.4g}</b>]'
        else:
            rng = ' (linspace)'
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">axis</span> '
            f'<b>{_html.escape(repr(ax.label))}</b>'
            f'  idx={ax.index}  size={ax.size}'
            f'{rng}{units_str}')

    for i, (arr, label) in enumerate(zip(dwa.data, dwa.labels)):
        if arr.size > 0:
            stats = (f'min=<b>{float(arr.min()):.4g}</b>'
                     f'  max=<b>{float(arr.max()):.4g}</b>'
                     f'  mean=<b>{float(arr.mean()):.4g}</b>')
        else:
            stats = '(empty)'
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">data[{i}]</span>'
            f' <b>{_html.escape(label)}</b>'
            f' {arr.dtype}  {stats}')

    header = '<span style="color:#1a2f6b"><b>DataWithAxes</b></span> — sent to viewer'
    body = '<br>'.join('&nbsp;&nbsp;' + r for r in rows)
    return header + '<br>' + body


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

    def set_completions(self, words: list[str]) -> None:
        self._completions = sorted(set(words))
        self._update_popup()

    def add_completions(self, words: list[str]) -> None:
        self._completions = sorted(set(self._completions) | set(words))
        self._update_popup()

    def _brace_prefix(self) -> str | None:
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        brace = text.rfind('{', 0, pos)
        if brace < 0:
            return None
        if text.find('}', brace, pos) >= 0:
            return None
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
        self._xr_ctx: dict = {}   # keyed by full_name; values are xr.Dataset
        self._setup_ui()
        if h5_path:
            self.path_edit.setText(h5_path)
            self._load_keys()

    def _setup_ui(self):
        self.setWindowTitle('H5 Formula Debugger')
        self.resize(1200, 750)
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

        ll.addWidget(_bold('H5 datasets  (double-click to insert):'))
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
            '<b>Syntax (xarray):</b> &nbsp;'
            '<code>{key}</code> → <b>xr.Dataset</b> &nbsp;·&nbsp;'
            '<code>{key}["var"]</code> → <b>xr.DataArray</b> — use for math &nbsp;·&nbsp;'
            '<code>.mean("dim")</code> &nbsp;'
            '<code>.isel(dim=N)</code> &nbsp;'
            '<code>.sel(dim=v)</code> &nbsp;'
            '<code>.rolling(...).mean()</code> &nbsp;·&nbsp;'
            'cross-ref: <code>a = {key}["var"] * 2</code> then <code>{a}["a"]</code> &nbsp;·&nbsp;'
            'type <code>{</code> to autocomplete'
        )
        hint.setWordWrap(True)
        rl.addWidget(hint)

        rl.addWidget(_bold('Formulas  (one per line,  name = expr  or bare expr):'))
        self.formula_edit = FormulaEditor()
        self.formula_edit.setPlaceholderText(
            '# {key} → xr.Dataset;  {key}["var"] → xr.DataArray\n'
            'scaled   = {origin/name}["CH00"] * 2\n'
            'mean_t   = {origin/name}["CH00"].mean("time")\n'
            'frame5   = {origin/name}["CH00"].isel(time=5)\n'
            '\n'
            '# Cross-reference: {mean_t} → xr.Dataset with var "mean_t"\n'
            'shifted  = {mean_t}["mean_t"] + 100\n'
            '\n'
            '# numpy ufuncs work on DataArray\n'
            'sqrted   = np.sqrt({origin/name}["CH00"])\n'
            '\n'
            '# raw numpy via .values\n'
            'grad     = np.gradient({origin/name}["CH00"].values)\n'
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
        splitter.setSizes([320, 880])
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

                # Build xarray context from in-memory DTE (file already closed)
                self._xr_ctx = {}
                try:
                    for full_name in names:
                        dwa = self._dte_from_h5.get_data_from_full_name(full_name)
                        self._xr_ctx[full_name] = dwa.to_xarray()
                except Exception:
                    self._xr_ctx = {}   # xarray not installed or conversion failed

                self.keys_list.clear()
                for n in names:
                    self.keys_list.addItem(n)
                self.vars_list.clear()
                self.formula_edit.set_completions(names)

                xr_note = '' if self._xr_ctx else ' <i>(xarray not available — DWA mode)</i>'
                self._log(
                    f'<span style="color:green"><b>Loaded</b> {len(names)} dataset(s) '
                    f'via {backend}</span>{xr_note}<br>'
                    + ''.join(f'&nbsp;&nbsp;{_html.escape(n)}<br>' for n in names)
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
            self._log(f'<b>{backend}:</b><br><pre>{_html.escape(tb)}</pre>')

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

        if self._xr_ctx:
            self._compute_xarray(formulae)
        else:
            self._compute_dwa(formulae)

        self._log('<hr>')

    def _compute_xarray(self, formulae):
        """Evaluate formulas using the xarray context (primary path)."""
        import xarray as xr

        # Fresh copy of the H5 context each run so repeated Compute calls
        # don't accumulate stale intermediate variables.
        xr_ctx = dict(self._xr_ctx)
        defined_this_run: list[str] = []

        for out_name, expr in formulae:
            formula_eval, _ = replace_names_in_formula_xr(expr)
            self._log(
                f'<b>[{_html.escape(out_name)}]</b> &nbsp; '
                f'<code>{_html.escape(expr)}</code><br>'
                f'<span style="color:#888">&nbsp;&nbsp;eval: '
                f'<code>{_html.escape(formula_eval)}</code></span>')
            try:
                result = eval(formula_eval, {'np': np, 'xr': xr, '_xr': xr_ctx})
                dwa = _wrap_result(result, out_name)

                # Store raw xarray result in context (no DWA round-trip)
                if isinstance(result, xr.DataArray):
                    xr_ctx[out_name] = result.to_dataset(name=out_name)
                elif isinstance(result, xr.Dataset):
                    xr_ctx[out_name] = result
                else:
                    try:
                        ds = dwa.to_xarray()
                        xr_ctx[out_name] = ds.assign_attrs(
                            {k: v for k, v in ds.attrs.items()
                             if not k.startswith('pymodaq_')})
                    except Exception:
                        pass

                defined_this_run.append(out_name)

                # ── Rich output ──────────────────────────────────────────────
                ds_in_ctx = xr_ctx.get(out_name)
                if ds_in_ctx is not None:
                    self._log(_format_xr_html(ds_in_ctx, out_name))
                self._log(_format_dwa_html(dwa))

            except Exception as exc:
                import traceback
                tb = _html.escape(traceback.format_exc())
                self._log(
                    f'&nbsp;&nbsp;<span style="color:red"><b>ERROR:</b> '
                    f'{_html.escape(str(exc))}</span>'
                    f'<br><details><summary style="color:#888">traceback</summary>'
                    f'<pre style="font-size:9pt">{tb}</pre></details>')

            self._log('')   # blank line between formulas

        self._update_vars_panel(defined_this_run)

    def _compute_dwa(self, formulae):
        """Fallback: evaluate formulas using DataWithAxes context (no xarray)."""
        dte = FormulaDTE('Combined')
        for dwa in self._dte_from_h5.data:
            dte.append(dwa)

        defined_this_run: list[str] = []

        for out_name, expr in formulae:
            formula_to_eval, _ = replace_names_in_formula(expr)
            self._log(f'<b>[{_html.escape(out_name)}]</b> &nbsp; <code>{_html.escape(expr)}</code>')
            try:
                result = eval(formula_to_eval)   # np and dte in scope
                result = _wrap_result(result, out_name)
                dte.append(result)
                defined_this_run.append(out_name)
                self._log(_format_dwa_html(result))
            except Exception as exc:
                self._log(
                    f'&nbsp;&nbsp;<span style="color:red">ERROR: '
                    f'{_html.escape(str(exc))}</span>')

            self._log('')

        self._update_vars_panel(defined_this_run)

    def _update_vars_panel(self, new_names: list[str]):
        current = [self.vars_list.item(i).text()
                   for i in range(self.vars_list.count())]
        for name in new_names:
            if name not in current:
                self.vars_list.addItem(name)
        self.formula_edit.add_completions(new_names)

    def _log(self, html_str: str):
        self.output_edit.append(html_str)


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
