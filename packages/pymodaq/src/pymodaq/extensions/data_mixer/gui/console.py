"""Formula console for the DataMixer GUI.

Two-panel design
----------------
Formula Editor (always present)
    The "commit" surface — named formulas, ``{…}`` autocomplete, explicit
    "Compute & Store" button (Ctrl+Enter), "Clear" button, and a "Lazy"
    toggle (when dask is available).

IPython Scratchpad (if ``qtconsole`` installed)
    A pure playground: ``_xr`` is pre-loaded so you can explore freely.
    Nothing is auto-captured from it.  A "Restart Kernel" button resets
    the namespace without losing the H5 context.

Lazy evaluation
---------------
When *dask* is installed and the Lazy toggle is active, all inputs in the
evaluation context are ``.chunk()``-ed before the formula is evaluated.
Operations on dask-backed xarray objects build a computation graph rather
than running immediately, avoiding memory pressure for large datasets.
The OutputWidget shows ``[lazy]`` annotations and structure (dims, chunks,
dtype) without materialising any data.  Flip the toggle back to Eager mode
to get concrete min/max/mean statistics in the output.
"""
from __future__ import annotations

import html as _html
import re
import traceback as _traceback
from typing import Optional

import numpy as np
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QFont, QTextCursor, QSyntaxHighlighter, QTextCharFormat, QColor, QKeySequence
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTextEdit,
    QListWidget, QAbstractItemView, QSplitter, QLabel, QPushButton, QShortcut,
)

from pymodaq.extensions.data_mixer.parser import (
    replace_names_in_formula_xr,
    parse_named_formulae,
)
from pymodaq.extensions.data_mixer.gui.formatters import (
    _wrap_result, _format_xr_html, _format_xr_lazy_html,
)
from pymodaq_data.data import DataToExport



from qtpy.QtGui import QColor, QTextCharFormat, QPalette

def _fmt(color: QColor, bold=False, italic=False):
    fmt = QTextCharFormat()
    fmt.setForeground(color)
    if bold:
        fmt.setFontWeight(fmt.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


def adjust(color: QColor, factor: float) -> QColor:
    """
    factor > 1.0 → lighter
    factor < 1.0 → darker
    """
    c = QColor(color)
    h, s, l, a = c.getHsl()
    l = max(0, min(255, int(l * factor)))
    c.setHsl(h, s, l, a)
    return c

# ── Optional dependency flags ─────────────────────────────────────────────────

try:
    from qtconsole.inprocess import QtInProcessKernelManager
    from qtconsole.rich_jupyter_widget import RichJupyterWidget
    _QTCONSOLE = True
except ImportError:
    _QTCONSOLE = False

try:
    import dask as _dask_probe  # noqa: F401
    _DASK = True
    del _dask_probe
except ImportError:
    _DASK = False


# ── Lazy-detection helper ─────────────────────────────────────────────────────

def _is_lazy_ds(ds) -> bool:
    """Return True if *ds* is a dask-backed xarray object (not yet computed)."""
    if not _DASK:
        return False
    try:
        if hasattr(ds, 'chunks') and ds.chunks:
            return True
    except Exception:
        pass
    return False


# ── Fallback: syntax highlighter ─────────────────────────────────────────────

class FormulaHighlighter(QSyntaxHighlighter):
    """5-rule syntax highlighter for the formula editor."""

    def __init__(self, document, palette):
        super().__init__(document)

        self._palette = palette
        self._init_rules()

    def _init_rules(self,):
        base_text     = self._palette.color(QPalette.Text)
        secondary     = self._palette.color(QPalette.PlaceholderText)
        highlight     = self._palette.color(QPalette.Highlight)
        keyword_base  = self._palette.color(QPalette.Link)
        comment_color   = adjust(secondary, 1.0)
        string_color    = adjust(QColor(46, 139, 87), 1.2)   # stable green
        brace_color     = adjust(highlight, 1.1)
        identifier_color= base_text
        module_color    = adjust(keyword_base, 1.2)
        def _fmt(color: QColor, bold=False, italic=False):
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            if bold:
                fmt.setFontWeight(QFont.Bold)
            if italic:
                fmt.setFontItalic(True)
            return fmt
        self._rules = [
            # Comments
            (re.compile(r'#.*$'),
            _fmt(comment_color, italic=True)),

            # Strings
            (re.compile(r'"[^"]*"'),
            _fmt(string_color)),

            # Braced expressions
            (re.compile(r'\{[^}]*\}'),
            _fmt(brace_color, bold=True)),

            # Assignment LHS
            (re.compile(r'^\s*\w+\s*(?==)'),
            _fmt(identifier_color, bold=True)),

            # Known modules (np, xr)
            (re.compile(r'\b(np|xr)\b'),
            _fmt(module_color)),
        ]
    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

    def update_palette(self, palette):
        self._palette = palette
        self.rehighlight()

# ── Autocomplete editor ───────────────────────────────────────────────────────

class _FallbackEditor(QPlainTextEdit):
    """Plain-text formula editor with M1–M5 autocomplete popup.

    Autocomplete modes (regex state machine on text-before-cursor):

    Mode | Trigger                     | Candidates
    -----|-----------------------------|------------------
    M1   | inside ``{…}``              | all H5 + computed names
    M2   | after ``{h5name}["``        | data_vars of that H5 Dataset
    M3   | after ``}.`` or ``}[v].``   | static xarray method list
    M4   | after ``.mean("`` etc.      | dims of referenced object
    M5   | after ``.isel(`` / ``.sel(``| ``dim=`` stubs
    """

    _XR_METHODS = [
        'mean(', 'sum(', 'std(', 'min(', 'max(', 'median(',
        'isel(', 'sel(', 'where(', 'dropna(', 'fillna(',
        'rolling(', 'resample(', 'groupby(', 'coarsen(',
        'diff(', 'differentiate(', 'integrate(',
        'transpose(', 'squeeze(', 'expand_dims(', 'rename(',
        'assign_coords(', 'assign_attrs(', 'to_array(', 'to_dataset(',
        'values', 'dims', 'coords', 'attrs', 'shape', 'size', 'dtype',
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._h5_ctx: dict = {}
        self._computed: dict = {}
        self._all_names: list[str] = []

        self._popup = QListWidget(self)
        self._popup.setWindowFlags(Qt.ToolTip)
        self._popup.setFocusPolicy(Qt.NoFocus)
        self._popup.setFocusProxy(self)
        self._popup.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._popup.itemClicked.connect(self._do_complete)
        self._popup.hide()

        FormulaHighlighter(self.document(), self.palette())

    def set_context(self, h5_ctx: dict, computed: dict) -> None:
        self._h5_ctx = h5_ctx
        self._computed = computed
        self._all_names = list(h5_ctx.keys()) + list(computed.keys())

    def update_computed(self, name: str, ds) -> None:
        self._computed[name] = ds
        if name not in self._all_names:
            self._all_names.append(name)

    # ── completion detection ──────────────────────────────────────────────────

    def _text_before_cursor(self) -> str:
        cursor = self.textCursor()
        return self.toPlainText()[:cursor.position()]

    def _detect_completion(self) -> tuple[str, str, list[str]]:
        text = self._text_before_cursor()

        m1 = re.search(r'\{([^}]*)$', text)
        if m1:
            prefix = m1.group(1)
            names = [n for n in self._all_names if prefix.lower() in n.lower()]
            return ('M1', prefix, names)

        m2 = re.search(r'\{([^}]+)\}\["([^"]*)$', text)
        if m2:
            ds_name, prefix = m2.group(1), m2.group(2)
            ds = self._h5_ctx.get(ds_name)
            if ds is not None:
                candidates = [v for v in ds.data_vars if prefix.lower() in v.lower()]
                return ('M2', prefix, candidates)

        # M2b: after {h5name}["var"]["  — coordinate name completion
        m2b = re.search(r'\{([^}]+)\}\["([^"]+)"\]\["([^"]*)$', text)
        if m2b:
            ds_name, var_name, prefix = m2b.group(1), m2b.group(2), m2b.group(3)
            ds = self._h5_ctx.get(ds_name)
            if ds is not None and var_name in ds.data_vars:
                coords = list(ds[var_name].coords)
                candidates = [c for c in coords if prefix.lower() in c.lower()]
                return ('M2b', prefix, candidates)

        m3 = re.search(r'\}(\["[^"]+"\])?\.(\w*)$', text)
        if m3:
            prefix = m3.group(2)
            candidates = [m for m in self._XR_METHODS if m.lower().startswith(prefix.lower())]
            return ('M3', prefix, candidates)

        m4 = re.search(
            r'\.(mean|sum|std|min|max|median|diff|integrate|differentiate)\("([^"]*)$', text)
        if m4:
            prefix = m4.group(2)
            dims = self._dims_for_context(text)
            candidates = [d for d in dims if d.lower().startswith(prefix.lower())]
            return ('M4', prefix, candidates)

        m5 = re.search(r'\.(isel|sel)\([^)]*$', text)
        if m5:
            dims = self._dims_for_context(text)
            prefix_m = re.search(r'(\w*)$', text)
            prefix = prefix_m.group(1) if prefix_m else ''
            candidates = [f'{d}=' for d in dims if d.lower().startswith(prefix.lower())]
            return ('M5', prefix, candidates)

        return ('NONE', '', [])

    def _collect_dims(self) -> list[str]:
        dims: set[str] = set()
        for ds in list(self._h5_ctx.values()) + list(self._computed.values()):
            try:
                dims.update(ds.dims.keys())
            except Exception:
                pass
        return sorted(dims)

    def _dims_for_context(self, text: str) -> list[str]:
        """Return dims relevant to the innermost ``{name}`` reference in *text*.

        Resolution priority:
          P1/P2: ``{h5}["var"]…``  → dims of that specific DataArray
          P3:    ``{name}…``       → dims of the Dataset (computed or H5)
          fallback:                  all dims from all datasets
        """
        # P1/P2: {h5name}["var_name"]… — resolve to a specific DataArray
        m = re.search(r'\{([^}]+)\}\["([^"]+)"\][^{]*$', text)
        if m:
            ds = self._h5_ctx.get(m.group(1))
            if ds is not None and m.group(2) in ds.data_vars:
                return list(ds[m.group(2)].dims)
        # P3: {name}… — computed Dataset or bare H5 Dataset
        m = re.search(r'\{([^}]+)\}[^{]*$', text)
        if m:
            name = m.group(1)
            for ctx in (self._computed, self._h5_ctx):
                ds = ctx.get(name)
                if ds is not None:
                    try:
                        return list(ds.dims.keys())
                    except Exception:
                        pass
        return self._collect_dims()

    # ── popup management ─────────────────────────────────────────────────────

    def _update_popup(self) -> None:
        mode, prefix, candidates = self._detect_completion()
        if mode == 'NONE' or not candidates:
            self._popup.hide()
            return
        self._popup.clear()
        for c in candidates:
            self._popup.addItem(c)
        self._popup.setCurrentRow(0)
        row_h = self._popup.sizeHintForRow(0) + 2
        self._popup.resize(400, min(len(candidates) * row_h + 4, 260))
        self._popup.move(self.mapToGlobal(self.cursorRect().bottomLeft()))
        self._popup.show()
        self._popup._mode = mode
        self._popup._prefix = prefix

    def _do_complete(self, item) -> None:
        mode = getattr(self._popup, '_mode', 'M1')
        prefix = getattr(self._popup, '_prefix', '')
        text = item.text()
        cursor = self.textCursor()
        pos = cursor.position()
        full = self.toPlainText()

        if mode == 'M1':
            brace = full.rfind('{', 0, pos)
            if brace >= 0:
                cursor.setPosition(brace + 1)
                cursor.setPosition(pos, QTextCursor.KeepAnchor)
                cursor.insertText(text + '}')
        elif mode in ('M2', 'M2b'):
            quote = full.rfind('"', 0, pos)
            if quote >= 0:
                cursor.setPosition(quote + 1)
                cursor.setPosition(pos, QTextCursor.KeepAnchor)
                cursor.insertText(text + '"]')
        elif mode in ('M3', 'M4', 'M5'):
            start = pos - len(prefix)
            cursor.setPosition(start)
            cursor.setPosition(pos, QTextCursor.KeepAnchor)
            cursor.insertText(text)

        self.setTextCursor(cursor)
        self._popup.hide()
        self.setFocus()

    # ── key events ───────────────────────────────────────────────────────────

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


# ── Output widget ─────────────────────────────────────────────────────────────

class OutputWidget(QTextEdit):
    """Read-only HTML output panel."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setReadOnly(True)
        f = QFont('Courier New')
        f.setPointSize(9)
        self.setFont(f)

    def log(self, html_str: str) -> None:
        self.append(html_str)

    def clear_output(self) -> None:
        self.clear()


# ── Public console widget ─────────────────────────────────────────────────────

class FormulaConsole(QWidget):
    """Formula Editor + optional IPython Scratchpad.

    Signals
    -------
    variable_stored_sig(name, ds, formula)
        Emitted after a formula is successfully computed and stored.
        ``name`` is the variable name, ``ds`` is the resulting ``xr.Dataset``
        (may be dask-backed / lazy when the Lazy toggle is active),
        ``formula`` is the raw RHS expression string.
    """

    variable_stored_sig = Signal(str, object, str)   # (name, ds, formula_expr)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._h5_ctx: dict = {}
        self._computed: dict = {}
        self._lazy_mode: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _QTCONSOLE:
            outer = QSplitter(Qt.Vertical)
            outer.addWidget(self._build_formula_widget())
            outer.addWidget(self._build_ipython_widget())
            outer.setSizes([400, 300])
            layout.addWidget(outer)
        else:
            layout.addWidget(self._build_formula_widget())

    # ── Formula editor (always present) ───────────────────────────────────────

    def _build_formula_widget(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 4)

        label = QLabel('<b>Named Formulas</b>  (one per line,  <code>name = expr</code>)')
        label.setTextFormat(Qt.RichText)
        vbox.addWidget(label)

        self._editor = _FallbackEditor(w)
        self._editor.setPlaceholderText(
            '# Type {  to autocomplete variable names\n'
            'a = {origin/name}["CH00"].mean("time")\n'
            'b = {a} + 1\n'
        )
        f = QFont('Courier New')
        f.setPointSize(10)
        self._editor.setFont(f)
        vbox.addWidget(self._editor, stretch=1)

        # Button row: [Compute & Store]  [Clear]  [Lazy toggle if dask]
        btn_row = QHBoxLayout()

        compute_btn = QPushButton('\u25b6  Compute & Store  (Ctrl+Enter)')
        compute_btn.clicked.connect(self._compute_and_store)
        btn_row.addWidget(compute_btn, stretch=1)

        clear_btn = QPushButton('\u27f3  Clear')
        clear_btn.setToolTip('Clear computed variables and output (keeps formula text)')
        clear_btn.clicked.connect(self._clear_computed)
        btn_row.addWidget(clear_btn)

        if _DASK:
            self._lazy_btn = QPushButton('Lazy')
            self._lazy_btn.setCheckable(True)
            self._lazy_btn.setChecked(False)
            self._lazy_btn.setToolTip(
                'Lazy mode (dask): build a computation graph instead of running immediately.\n'
                'Results show structure and chunk layout — no data is loaded into memory.')
            self._lazy_btn.toggled.connect(self._on_lazy_toggled)
            btn_row.addWidget(self._lazy_btn)
        else:
            self._lazy_btn = None

        vbox.addLayout(btn_row)

        self._output_widget = OutputWidget(w)
        self._output_widget.setMaximumHeight(140)
        vbox.addWidget(self._output_widget)

        QShortcut(QKeySequence('Ctrl+Return'), self._editor).activated.connect(
            self._compute_and_store)

        return w

    # ── IPython scratchpad (qtconsole only) ───────────────────────────────────

    def _build_ipython_widget(self) -> QWidget:
        self._km = QtInProcessKernelManager()
        self._km.start_kernel()
        kernel = self._km.kernel
        try:
            import xarray as xr
            kernel.shell.push({'np': np, 'xr': xr, '_xr': {}})
        except ImportError:
            kernel.shell.push({'np': np, '_xr': {}})

        self._kc = self._km.client()
        self._kc.start_channels()

        self._jupyter_widget = RichJupyterWidget()
        self._jupyter_widget.kernel_manager = self._km
        self._jupyter_widget.kernel_client = self._kc

        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 4, 0, 0)

        # Header row with label + restart button
        header_row = QHBoxLayout()
        label = QLabel(
            '<b>IPython Scratchpad</b>  '
            '(<code>_xr</code> pre-loaded \u2014 explore freely)')
        label.setTextFormat(Qt.RichText)
        header_row.addWidget(label, stretch=1)

        restart_btn = QPushButton('\u27f3  Restart Kernel')
        restart_btn.setToolTip(
            'Reset the IPython namespace.\n'
            'H5 context and computed variables are re-pushed automatically.')
        restart_btn.clicked.connect(self._restart_kernel)
        header_row.addWidget(restart_btn)

        vbox.addLayout(header_row)
        vbox.addWidget(self._jupyter_widget, stretch=1)
        return w

    # ── Lazy toggle ───────────────────────────────────────────────────────────

    def _on_lazy_toggled(self, checked: bool) -> None:
        self._lazy_mode = checked
        if self._lazy_btn is not None:
            self._lazy_btn.setStyleSheet(
                'font-weight: bold; color: #1a5cb5;' if checked else '')

    # ── Clear computed ────────────────────────────────────────────────────────

    def _clear_computed(self) -> None:
        """Clear all computed variables and reset the output log."""
        self._computed.clear()
        self._editor.set_context(self._h5_ctx, self._computed)
        self._output_widget.clear_output()
        if _QTCONSOLE:
            self._km.kernel.shell.user_ns['_xr'] = dict(self._h5_ctx)

    # ── Restart IPython kernel ────────────────────────────────────────────────

    def _restart_kernel(self) -> None:
        """Reset the in-process IPython kernel namespace (kernel stays alive)."""
        kernel = self._km.kernel
        kernel.shell.reset()
        try:
            import xarray as xr
            kernel.shell.push({'np': np, 'xr': xr, '_xr': dict(self._h5_ctx)})
        except ImportError:
            kernel.shell.push({'np': np, '_xr': dict(self._h5_ctx)})
        xr_ns = kernel.shell.user_ns['_xr']
        for name, ds in self._computed.items():
            xr_ns[name] = ds

    # ── Compute & Store ───────────────────────────────────────────────────────

    def _compute_and_store(self) -> None:
        """Parse editor, evaluate each formula, store results."""
        text = self._editor.toPlainText()
        pairs = parse_named_formulae(text)
        if not pairs:
            return

        xr_ctx = {**self._h5_ctx, **self._computed}
        computed_names = set(self._computed.keys())

        try:
            import xarray as xr
        except ImportError:
            xr = None

        # In lazy mode, chunk all inputs so operations build a dask graph
        if self._lazy_mode and _DASK and xr is not None:
            xr_ctx_eval: dict = {}
            for k, v in xr_ctx.items():
                if hasattr(v, 'chunk'):
                    try:
                        xr_ctx_eval[k] = v.chunk()
                    except Exception:
                        xr_ctx_eval[k] = v
                else:
                    xr_ctx_eval[k] = v
        else:
            xr_ctx_eval = xr_ctx

        for name, expr in pairs:
            try:
                formula_eval, _ = replace_names_in_formula_xr(
                    expr, computed_names=computed_names)
                ns = {'np': np, '_xr': xr_ctx_eval}
                if xr is not None:
                    ns['xr'] = xr

                result = eval(formula_eval, ns)

                # Convert to xr.Dataset for storage.
                # For xarray results we avoid _wrap_result (which calls
                # DataWithAxes.from_xarray and materialises dask arrays).
                if xr is not None and isinstance(result, xr.DataArray):
                    ds = result.to_dataset(name=name)
                elif xr is not None and isinstance(result, xr.Dataset):
                    ds = result
                else:
                    # Non-xarray result: wrap via DWA then convert
                    try:
                        dwa = _wrap_result(result, name)
                        ds = dwa.to_xarray()
                    except Exception:
                        ds = None

                if ds is not None:
                    xr_ctx[name] = ds
                    xr_ctx_eval[name] = ds
                    computed_names.add(name)
                    self._computed[name] = ds
                    self._editor.update_computed(name, ds)
                    if _QTCONSOLE:
                        self._km.kernel.shell.user_ns['_xr'][name] = ds
                    self.variable_stored_sig.emit(name, ds, expr)

                    lazy = _is_lazy_ds(ds)
                    if lazy:
                        badge = ' <span style="color:#1a5cb5"><b>[lazy]</b></span>'
                        color, icon = '#1a5cb5', '~'
                        fmt_html = _format_xr_lazy_html(ds, name)
                    else:
                        badge = ''
                        color, icon = '#1a6b1a', '\u2713'
                        fmt_html = _format_xr_html(ds, name)

                    self._output_widget.log(
                        f'<span style="color:{color}"><b>{icon} {_html.escape(name)}</b></span>'
                        f'{badge} ' + fmt_html)
                else:
                    self._output_widget.log(
                        f'<span style="color:#c87000"><b>\u26a0 {_html.escape(name)}</b></span> '
                        f'result could not be stored as xarray Dataset')

            except Exception as exc:
                tb = _html.escape(_traceback.format_exc())
                self._output_widget.log(
                    f'<span style="color:red"><b>\u2717 {_html.escape(name)}:</b> '
                    f'{_html.escape(str(exc))}</span>'
                    f'<br><details><summary style="color:#888">traceback</summary>'
                    f'<pre style="font-size:9pt">{tb}</pre></details>')

    # ── Public API ────────────────────────────────────────────────────────────

    def push_h5_context(self, xr_ctx: dict) -> None:
        """Inject the H5 xarray context dict into the console namespace."""
        self._h5_ctx = xr_ctx
        self._editor.set_context(self._h5_ctx, self._computed)
        if _QTCONSOLE:
            self._km.kernel.shell.user_ns['_xr'].update(xr_ctx)

    def push_computed(self, name: str, ds) -> None:
        """Add or update a computed variable in the console namespace."""
        self._computed[name] = ds
        self._editor.update_computed(name, ds)
        if _QTCONSOLE:
            self._km.kernel.shell.user_ns['_xr'][name] = ds

    def insert_at_cursor(self, text: str) -> None:
        """Insert *text* into the formula editor at the current cursor position."""
        self._editor.insertPlainText(text)
        self._editor.setFocus()

    def get_computed_names(self) -> set:
        """Return the set of currently defined computed variable names."""
        return set(self._computed.keys())

    def get_output_widget(self) -> Optional[OutputWidget]:
        """Return the output widget."""
        return self._output_widget
