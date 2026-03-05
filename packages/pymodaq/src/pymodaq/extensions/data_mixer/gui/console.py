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
from qtpy.QtCore import Qt, Signal, QSize
from qtpy.QtGui import QFont, QTextCursor, QSyntaxHighlighter, QTextCharFormat, QColor, QKeySequence
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTextEdit,
    QListWidget, QAbstractItemView, QSplitter, QLabel, QPushButton, QShortcut,
    QFileDialog, QToolBar, QAction, QSizePolicy,
)

from pymodaq.extensions.data_mixer.parser import (
    replace_names_in_formula_xr,
    parse_named_formulae,
)
from pymodaq.extensions.data_mixer.gui.formatters import (
    _format_xr_html, _format_xr_lazy_html,
)
from pymodaq_data.h5modules import wrap_result
from pymodaq_data.data import DataToExport
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq_gui.utils.styling import create_icon

logger = set_logger(get_module_name(__file__))



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
        base_text     = self._palette.color(QPalette.ColorRole.Text)
        secondary     = self._palette.color(QPalette.ColorRole.PlaceholderText)
        highlight     = self._palette.color(QPalette.ColorRole.Highlight)
        keyword_base  = self._palette.color(QPalette.ColorRole.Link)
        comment_color   = adjust(secondary, 1.0)
        string_color    = adjust(QColor(46, 139, 87), 1.2)   # stable green
        brace_color     = adjust(highlight, 1.1)
        identifier_color= base_text
        module_color    = adjust(keyword_base, 1.2)
        def _fmt(color: QColor, bold=False, italic=False):
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            if bold:
                fmt.setFontWeight(QFont.Weight.Bold)
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
    M1   | ``@`` prefix                | all H5 + computed names  (inserts ``{name}``)
    M2   | after ``{h5name}["``        | data_vars of that H5 Dataset
    M3   | after ``}.``, ``].``, ``).`` | static xarray method list
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
        self._h5_loader = None   # optional (rel_path) -> xr.Dataset | None

        self._popup = QListWidget(self)
        self._popup.setWindowFlags(Qt.WindowType.ToolTip)
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setFocusProxy(self)
        self._popup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._popup.itemClicked.connect(self._do_complete)
        self._popup.hide()

        # Track the text-position of the @ trigger that the user dismissed with
        # Escape, so we do not re-show the popup for the same trigger session.
        self._popup_dismissed_at = -1

        FormulaHighlighter(self.document(), self.palette())
        QShortcut(QKeySequence('Ctrl+/'), self).activated.connect(self._toggle_comment)

    def set_context(self, h5_ctx: dict, computed: dict) -> None:
        self._h5_ctx = h5_ctx
        self._computed = computed
        self._all_names = list(h5_ctx.keys()) + list(computed.keys())

    def update_computed(self, name: str, ds) -> None:
        self._computed[name] = ds
        if name not in self._all_names:
            self._all_names.append(name)

    def remove_computed(self, name: str) -> None:
        self._computed.pop(name, None)
        try:
            self._all_names.remove(name)
        except ValueError:
            pass

    # ── completion detection ──────────────────────────────────────────────────

    def _text_before_cursor(self) -> str:
        cursor = self.textCursor()
        return self.toPlainText()[:cursor.position()]

    def _detect_completion(self, _text: str | None = None) -> tuple[str, str, list[str]]:
        """Determine the current autocomplete mode from text before the cursor.

        The optional *_text* parameter is used in tests to inject a fixed
        string without needing a real QPlainTextEdit cursor.
        """
        text = _text if _text is not None else self._text_before_cursor()

        m1 = re.search(r'@(\S*)$', text)
        if m1:
            prefix = m1.group(1)
            names = [n for n in self._all_names if prefix.lower() in n.lower()]
            return ('M1', prefix, names)

        m2 = re.search(r'\{([^}]+)\}\["([^"]*)$', text)
        if m2:
            ds_name, prefix = m2.group(1), m2.group(2)
            # Prefer loaded datasets (computed or already-fetched H5)
            ds = self._computed.get(ds_name) or self._h5_ctx.get(ds_name)
            if ds is not None:
                candidates = [v for v in ds.data_vars if prefix.lower() in v.lower()]
                return ('M2', prefix, candidates)
            # Fallback: dataset not yet loaded — infer channel name from the
            # last path component (e.g. "CH00" from "Scan001/Det/Data1D/CH00")
            inferred = ds_name.rsplit('/', 1)[-1]
            if prefix.lower() in inferred.lower():
                return ('M2', prefix, [inferred])

        # M2b: after {h5name}["var"]["  — coordinate name completion
        m2b = re.search(r'\{([^}]+)\}\["([^"]+)"\]\["([^"]*)$', text)
        if m2b:
            ds_name, var_name, prefix = m2b.group(1), m2b.group(2), m2b.group(3)
            ds = self._computed.get(ds_name) or self._h5_ctx.get(ds_name)
            if ds is not None and var_name in ds.data_vars:
                coords = list(ds[var_name].coords)
                candidates = [c for c in coords if prefix.lower() in c.lower()]
                return ('M2b', prefix, candidates)

        m3 = re.search(r'[}\])](\["[^"]+"\])?\.(\w*)$', text)
        if m3:
            prefix = m3.group(2)
            candidates = [m for m in self._XR_METHODS if m.lower().startswith(prefix.lower())]
            return ('M3', prefix, candidates)

        m4 = re.search(
            r'\.(mean|sum|std|min|max|median|squeeze|diff|integrate|differentiate)\("([^"]*)$', text)
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

    def _consumed_dims(self, text: str) -> set[str]:
        """Return dim names already consumed by reductions in the expression chain.

        Detects patterns like ``.mean("x")``, ``.squeeze("x")``,
        ``.isel(x=…)``, ``.sel(x=…)`` and returns the dim names used,
        so they can be excluded from subsequent completion suggestions.

        Only the *current line* is examined to avoid cross-formula contamination
        (a ``.mean("time")`` on a previous line must not suppress ``time`` here).
        Operations that merely transform a dimension without removing it
        (``diff``, ``differentiate``) are intentionally excluded.
        """
        # Restrict to the current line so previous formula lines don't bleed in.
        line = text.rsplit('\n', 1)[-1]
        consumed: set[str] = set()
        # Aggregations that remove the dimension entirely.
        # Use [^"]+ instead of \w+ so dim names that contain spaces are matched.
        for m in re.finditer(
            r'\.(mean|sum|std|min|max|median|squeeze|integrate)\("([^"]+)"',
            line,
        ):
            consumed.add(m.group(2))
        # .isel(dim=…) / .sel(dim=…) with scalar index also remove the dim
        for m in re.finditer(r'\.(isel|sel)\(([^)]*)\)', line):
            for kw in re.finditer(r'(\w+)\s*=', m.group(2)):
                consumed.add(kw.group(1))
        return consumed

    def _dims_for_context(self, text: str) -> list[str]:
        """Return dims relevant to the innermost ``{name}`` reference in *text*,
        excluding dims already consumed by reductions earlier in the chain.

        Resolution priority:
          P1/P2: ``{name}["var"]…``  → dims of that specific DataArray
          P3:    ``{name}…``         → dims of the Dataset (computed or H5)
          fallback:                    all dims from all loaded datasets

        When a dataset entry is ``None`` (not yet loaded), ``_h5_loader`` is
        called on demand and the result is cached back into ``_h5_ctx``.
        """
        consumed = self._consumed_dims(text)

        def _resolve(name: str):
            """Return dataset for *name*, loading on demand if needed."""
            ds = self._computed.get(name) or self._h5_ctx.get(name)
            if ds is None and self._h5_loader is not None:
                try:
                    ds = self._h5_loader(name)
                    if ds is not None:
                        self._h5_ctx[name] = ds
                except Exception:
                    pass
            return ds

        # P1/P2: {name}["var_name"]… — resolve to a specific DataArray
        m = re.search(r'\{([^}]+)\}\["([^"]+)"\][^{]*$', text)
        if m:
            ds = _resolve(m.group(1))
            if ds is not None and m.group(2) in ds.data_vars:
                return [d for d in ds[m.group(2)].dims if d not in consumed]
        # P3: {name}… — computed Dataset or bare H5 Dataset
        m = re.search(r'\{([^}]+)\}[^{]*$', text)
        if m:
            ds = _resolve(m.group(1))
            if ds is not None:
                try:
                    return [d for d in ds.dims.keys() if d not in consumed]
                except Exception:
                    pass
        return [d for d in self._collect_dims() if d not in consumed]

    # ── popup management ─────────────────────────────────────────────────────

    def _update_popup(self) -> None:
        mode, prefix, candidates = self._detect_completion()
        if mode != 'M1':
            # Any non-M1 mode (including NONE) resets the dismissed state so
            # the next @ the user types will show the popup again.
            self._popup_dismissed_at = -1
        if mode == 'NONE' or not candidates:
            self._popup.hide()
            return
        if mode == 'M1':
            # Find the position of the triggering @ character so we can track
            # whether the user already dismissed the popup for this trigger.
            text_before = self._text_before_cursor()
            m = re.search(r'@(\S*)$', text_before)
            trigger_start = m.start() if m else -1
            self._popup._trigger_start = trigger_start
            if self._popup_dismissed_at >= 0 and trigger_start == self._popup_dismissed_at:
                return  # user pressed Escape here — don't re-show
        else:
            self._popup._trigger_start = -1
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
        # Text that already follows the cursor — used to avoid duplicating
        # closing chars when the user edits inside an existing completion.
        rest = full[pos:]

        if mode == 'M1':
            # Replace @<prefix> with {completion} — the @ trigger is not kept.
            at_pos = full.rfind('@', 0, pos)
            if at_pos >= 0:
                cursor.setPosition(at_pos)
                cursor.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText('{' + text + '}')
        elif mode in ('M2', 'M2b'):
            quote = full.rfind('"', 0, pos)
            if quote >= 0:
                cursor.setPosition(quote + 1)
                cursor.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
                if rest.startswith('"]'):
                    suffix = ''
                elif rest.startswith(']'):
                    suffix = '"'
                else:
                    suffix = '"]'
                cursor.insertText(text + suffix)
        elif mode == 'M3':
            start = pos - len(prefix)
            cursor.setPosition(start)
            cursor.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
            if text.endswith('('):
                # Method: auto-close the paren and place cursor inside
                if rest.startswith(')'):
                    # Paren already present — just insert the method name,
                    # cursor lands between '(' and the existing ')'.
                    cursor.insertText(text)
                else:
                    cursor.insertText(text + ')')
                    cursor.setPosition(cursor.position() - 1)
            else:
                # Property attribute (values, dims, …): insert as-is
                cursor.insertText(text)
        elif mode == 'M4':
            start = pos - len(prefix)
            cursor.setPosition(start)
            cursor.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
            # Close the opened string quote and the method paren,
            # skipping whichever closing chars are already present after cursor.
            if rest.startswith('")'):
                suffix = ''           # both already present
            elif rest.startswith('"'):
                suffix = ')'          # string closed, paren missing
            elif rest.startswith(')'):
                suffix = '"'          # paren present (e.g. typed .mean()), just close string
            else:
                suffix = '")'
            cursor.insertText(text + suffix)
        elif mode == 'M5':
            start = pos - len(prefix)
            cursor.setPosition(start)
            cursor.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
            # Insert dim= stub; user types the value next
            cursor.insertText(text)

        self.setTextCursor(cursor)
        self._popup.hide()
        self.setFocus()

    # ── comment toggle ────────────────────────────────────────────────────────

    def _toggle_comment(self) -> None:
        """Toggle ``# `` comment prefix on selected lines (or current line)."""
        cursor = self.textCursor()
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()

        c = QTextCursor(self.document())
        c.setPosition(sel_start)
        first_block = c.blockNumber()
        c.setPosition(sel_end)
        last_block = c.blockNumber()
        # Don't include a trailing block if the selection ends at its very start
        if c.atBlockStart() and last_block > first_block:
            last_block -= 1

        # Determine whether all non-empty lines in range are already commented
        c.setPosition(sel_start)
        c.movePosition(QTextCursor.StartOfBlock)
        all_commented = True
        for _ in range(last_block - first_block + 1):
            line = c.block().text()
            if line.strip() and not line.lstrip().startswith('#'):
                all_commented = False
                break
            if not c.movePosition(QTextCursor.NextBlock):
                break

        # Apply the toggle
        c.setPosition(sel_start)
        c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        c.beginEditBlock()
        for _ in range(last_block - first_block + 1):
            c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            line = c.block().text()
            indent = len(line) - len(line.lstrip())
            stripped = line.lstrip()
            if all_commented:
                if stripped.startswith('# '):
                    c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, indent)
                    c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 2)
                    c.removeSelectedText()
                elif stripped.startswith('#'):
                    c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, indent)
                    c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                    c.removeSelectedText()
            else:
                c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, indent)
                c.insertText('# ')
            if not c.movePosition(QTextCursor.MoveOperation.NextBlock):
                break
        c.endEditBlock()

    # ── line duplication ─────────────────────────────────────────────────────

    def _copy_lines(self, down: bool) -> None:
        """Duplicate selected lines (or current line) below (down=True) or above.

        Mirrors the VS Code Alt+Shift+Down / Alt+Shift+Up behaviour.
        """
        cursor = self.textCursor()
        c = QTextCursor(self.document())

        # Expand selection to whole-line boundaries
        c.setPosition(cursor.selectionStart())
        c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        first_pos = c.position()

        c.setPosition(cursor.selectionEnd())
        # If the selection ends exactly at a block start (empty trailing line),
        # don't include that line in the copied range.
        if c.atBlockStart() and c.position() > cursor.selectionStart():
            c.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        last_pos = c.position()

        # Extract text (QTextCursor uses \u2029 as paragraph separator)
        c.setPosition(first_pos)
        c.setPosition(last_pos, QTextCursor.MoveMode.KeepAnchor)
        lines_text = c.selectedText().replace('\u2029', '\n')

        c.beginEditBlock()
        if down:
            c.setPosition(last_pos)
            c.insertText('\n' + lines_text)
            new_start = last_pos + 1
            new_end = new_start + len(lines_text)
        else:
            c.setPosition(first_pos)
            c.insertText(lines_text + '\n')
            new_start = first_pos
            new_end = first_pos + len(lines_text)
        c.endEditBlock()

        c.setPosition(new_start)
        c.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(c)

    # ── key events ───────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        if self._popup.isVisible():
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self._popup.hide()
                # Remember which @ trigger was dismissed so _update_popup
                # does not re-show it on the next keystroke.
                self._popup_dismissed_at = getattr(self._popup, '_trigger_start', -1)
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                item = self._popup.currentItem()
                if item:
                    self._do_complete(item)
                return
            if key == Qt.Key.Key_Down:
                self._popup.setCurrentRow(
                    (self._popup.currentRow() + 1) % self._popup.count())
                return
            if key == Qt.Key.Key_Up:
                self._popup.setCurrentRow(
                    (self._popup.currentRow() - 1) % self._popup.count())
                return
        # Alt+Shift+Down/Up: duplicate current lines below/above (VS Code style)
        mods = event.modifiers()
        if mods == (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier):
            if event.key() == Qt.Key.Key_Down:
                self._copy_lines(down=True)
                return
            if event.key() == Qt.Key.Key_Up:
                self._copy_lines(down=False)
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
    clear_computed_sig  = Signal()                    # request full clear (routed via DataMixerGUI)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._h5_ctx: dict = {}
        self._computed: dict = {}
        self._computed_formulas: dict = {}   # name → raw RHS expression string
        self._lazy_mode: bool = False
        self._lazy_action: Optional[QAction] = None
        self._validation_label: Optional[QLabel] = None
        self._ipython_container: Optional[QWidget] = None
        self._ipython_action: Optional[QAction] = None
        self._outer_splitter: Optional[QSplitter] = None
        self._km = None   # kernel manager — created lazily on first IPython open
        # Optional on-demand H5 loader provided by DataMixerGUI.
        # Signature: loader(rel_path: str) -> xr.Dataset | None
        self._h5_loader = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        formula_widget = self._build_formula_widget()
        if _QTCONSOLE:
            self._outer_splitter = QSplitter(Qt.Orientation.Vertical)
            self._outer_splitter.addWidget(formula_widget)
            layout.addWidget(self._outer_splitter)
        else:
            layout.addWidget(formula_widget)

    # ── Formula editor (always present) ───────────────────────────────────────

    def _build_formula_widget(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 4)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(16, 16))

        compute_action = QAction('\u25b6  Compute & Store', toolbar)
        compute_action.setToolTip(
            'Evaluate formulas in the editor and store results  (Ctrl+Enter)')
        compute_action.triggered.connect(self._compute_and_store)
        compute_action.setIcon(create_icon('function'))
        toolbar.addAction(compute_action)

        toolbar.addSeparator()

        save_action = QAction('Save\u2026', toolbar)
        save_action.setToolTip('Save current formulas to a TOML file')
        save_action.triggered.connect(self._save_formulas)
        save_action.setIcon(create_icon('save_as'))
        toolbar.addAction(save_action)

        load_action = QAction('Load\u2026', toolbar)
        load_action.setToolTip('Load formulas from a TOML file (replaces editor content)')
        load_action.triggered.connect(self._load_formulas)
        load_action.setIcon(create_icon('folder_data'))
        toolbar.addAction(load_action)

        if _DASK:
            toolbar.addSeparator()
            self._lazy_action = QAction('Lazy', toolbar)
            self._lazy_action.setCheckable(True)
            self._lazy_action.setChecked(False)
            self._lazy_action.setToolTip(
                'Lazy mode (dask): build a computation graph instead of running immediately.\n'
                'Results show structure and chunk layout — no data is loaded into memory.')
            self._lazy_action.toggled.connect(self._on_lazy_toggled)
            toolbar.addAction(self._lazy_action)

        # Validation indicator — live formula status (updated on every keystroke)
        toolbar.addSeparator()
        self._validation_label = QLabel('')
        self._validation_label.setTextFormat(Qt.TextFormat.RichText)
        toolbar.addWidget(self._validation_label)

        # Expanding spacer pushes IPython toggle to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        if _QTCONSOLE:
            self._ipython_action = QAction('IPython \u25be', toolbar)
            self._ipython_action.setCheckable(True)
            self._ipython_action.setChecked(False)
            self._ipython_action.setToolTip('Show / hide the IPython scratchpad')
            self._ipython_action.toggled.connect(self._toggle_ipython)
            toolbar.addAction(self._ipython_action)

        vbox.addWidget(toolbar)

        # ── Editor ────────────────────────────────────────────────────────────
        self._editor = _FallbackEditor(w)
        self._editor.setPlaceholderText(
            '# Type @ to autocomplete variable names\n'
            'a = {origin/name}["CH00"].mean("time")\n'
            'b = {a} + 1\n'
        )
        self._editor.setToolTip(
            'Formula editor\n'
            'Ctrl+Enter / Ctrl+E  — Compute & Store\n'
            'Ctrl+Z / Ctrl+Y      — Undo / Redo\n'
            'Ctrl+/               — Toggle comment\n'
            'Alt+Shift+↓/↑        — Duplicate line down/up'
        )
        f = QFont('Courier New')
        f.setPointSize(10)
        self._editor.setFont(f)
        self._editor.textChanged.connect(self._validate_formulas)

        # ── Output section ────────────────────────────────────────────────────
        self._output_widget = OutputWidget(w)

        output_header = QHBoxLayout()
        output_header.setContentsMargins(0, 2, 0, 0)
        output_label = QLabel('Output')
        output_label.setStyleSheet('font-weight: bold; color: #555;')
        output_header.addWidget(output_label, stretch=1)
        clear_out_btn = QPushButton('\u2715 clear output')
        clear_out_btn.setFlat(True)
        clear_out_btn.setStyleSheet('color: #888; font-size: 9pt;')
        clear_out_btn.setToolTip('Clear the output panel')
        clear_out_btn.clicked.connect(self._output_widget.clear_output)
        output_header.addWidget(clear_out_btn)

        output_container = QWidget()
        out_vbox = QVBoxLayout(output_container)
        out_vbox.setContentsMargins(0, 0, 0, 0)
        out_vbox.setSpacing(2)
        out_vbox.addLayout(output_header)
        out_vbox.addWidget(self._output_widget)

        # Resizable splitter between editor and output
        inner_splitter = QSplitter(Qt.Orientation.Vertical)
        inner_splitter.addWidget(self._editor)
        inner_splitter.addWidget(output_container)
        inner_splitter.setStretchFactor(0, 3)
        inner_splitter.setStretchFactor(1, 1)

        vbox.addWidget(inner_splitter, stretch=1)

        QShortcut(QKeySequence('Ctrl+Return'), self._editor).activated.connect(
            self._compute_and_store)
        QShortcut(QKeySequence('Ctrl+Key_Enter'), self._editor).activated.connect(
            self._compute_and_store)
        QShortcut(QKeySequence('Ctrl+E'), self._editor).activated.connect(
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

    def _toggle_ipython(self, checked: bool) -> None:
        if checked:
            if self._ipython_container is None:
                # First open: build the widget and kernel now, attach to splitter
                self._ipython_container = self._build_ipython_widget()
                self._outer_splitter.addWidget(self._ipython_container)
            self._ipython_container.setVisible(True)
        else:
            if self._ipython_container is not None:
                self._ipython_container.setVisible(False)

    # ── Clear computed ────────────────────────────────────────────────────────

    def _clear_computed(self) -> None:
        """Request a full clear.

        Emits ``clear_computed_sig`` so that ``DataMixerGUI`` can sync the
        browser and every other component before calling ``reset_computed()``.
        The console does NOT touch ``self._computed`` here — DataMixerGUI
        owns the coordination and calls ``reset_computed()`` when ready.
        """
        self.clear_computed_sig.emit()

    def reset_computed(self) -> None:
        """Reset internal computed state.

        Called by ``DataMixerGUI`` after it has cleared the browser and its
        own tracking dicts.  Keeps the formula editor text intact.
        """
        self._computed.clear()
        self._computed_formulas.clear()
        self._editor.set_context(self._h5_ctx, self._computed)
        self._output_widget.clear_output()
        if self._km is not None:
            loaded = {k: v for k, v in self._h5_ctx.items() if v is not None}
            self._km.kernel.shell.user_ns['_xr'] = loaded

    # ── Restart IPython kernel ────────────────────────────────────────────────

    def _restart_kernel(self) -> None:
        """Reset the in-process IPython kernel namespace (kernel stays alive)."""
        kernel = self._km.kernel
        kernel.shell.reset()
        loaded_h5 = {k: v for k, v in self._h5_ctx.items() if v is not None}
        try:
            import xarray as xr
            kernel.shell.push({'np': np, 'xr': xr, '_xr': loaded_h5})
        except ImportError:
            kernel.shell.push({'np': np, '_xr': loaded_h5})
        xr_ns = kernel.shell.user_ns['_xr']
        for name, ds in self._computed.items():
            xr_ns[name] = ds

    # ── Compute & Store ───────────────────────────────────────────────────────

    def _compute_and_store(self) -> None:
        """Parse the editor text, evaluate each formula, store results."""
        pairs = parse_named_formulae(self._editor.toPlainText())
        if not pairs:
            return
        self._run_formula_pairs(pairs)

    def _run_formula_pairs(self, pairs: list) -> None:
        """Evaluate a list of (name, expr) pairs and store/emit results.

        Shared by ``_compute_and_store`` (editor-sourced pairs) and
        ``recompute_all`` (stored-formula pairs).
        """
        # Build eval context.  h5_ctx may contain None values for datasets that
        # haven't been loaded yet (names-only mode).  Ask the on-demand loader
        # to fetch each such entry; cache the result back into _h5_ctx so that
        # repeated evaluations don't trigger redundant file opens.
        xr_ctx: dict = {}
        for k, v in self._h5_ctx.items():
            if v is None and self._h5_loader is not None:
                try:
                    v = self._h5_loader(k)
                    if v is not None:
                        self._h5_ctx[k] = v          # cache for next call
                        if self._km is not None:      # sync IPython kernel
                            self._km.kernel.shell.user_ns['_xr'][k] = v
                except Exception as exc:
                    logger.warning(f'On-demand H5 loader failed for {k!r}: {exc}')
            if v is not None:
                xr_ctx[k] = v
        xr_ctx.update(self._computed)
        computed_names = set(self._computed.keys())
        # Names whose stored Dataset has a variable with the *same* name — i.e.
        # results that were DataArrays, wrapped via .to_dataset(name=name).
        # Only these can be safely auto-dereferenced as _xr["name"]["name"].
        # Dataset-derived results (e.g. from .mean() on a whole Dataset) keep
        # their original variable names and must stay as _xr["name"].
        da_computed_names: set = {
            n for n, ds in self._computed.items()
            if hasattr(ds, 'data_vars') and n in ds.data_vars
        }

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
                    expr, computed_names=da_computed_names)
                ns = {'np': np, '_xr': xr_ctx_eval}
                if xr is not None:
                    ns['xr'] = xr

                result = eval(formula_eval, ns)

                # Convert to xr.Dataset for storage.  Keep everything in xarray
                # to avoid materialising dask arrays through DataWithAxes.
                if xr is not None and isinstance(result, xr.DataArray):
                    ds = result.to_dataset(name=name)
                    da_computed_names.add(name)   # auto-deref safe for this name
                elif xr is not None and isinstance(result, xr.Dataset):
                    ds = result
                    # Dataset keeps its original variable names — not safe to deref
                else:
                    # Non-xarray result: coerce to xr.Dataset.
                    # Prefer a direct xarray path for arrays/scalars to avoid
                    # materialising dask graphs through DataWithAxes.
                    # Fall back to wrap_result → to_xarray for DataWithAxes.
                    try:
                        if xr is not None and isinstance(result, np.ndarray):
                            da = xr.DataArray(result, name=name)
                            ds = da.to_dataset(name=name)
                            da_computed_names.add(name)
                        elif xr is not None and isinstance(
                                result, (int, float, np.integer, np.floating, np.bool_)):
                            da = xr.DataArray(np.array([float(result)]), name=name)
                            ds = da.to_dataset(name=name)
                            da_computed_names.add(name)
                        else:
                            dwa = wrap_result(result, name)
                            ds = dwa.to_xarray()
                    except Exception:
                        ds = None

                if ds is not None:
                    xr_ctx[name] = ds
                    xr_ctx_eval[name] = ds
                    computed_names.add(name)
                    self._computed[name] = ds
                    self._computed_formulas[name] = expr
                    self._editor.update_computed(name, ds)
                    if self._km is not None:
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

    # ── Save / Load formulas (TOML) ───────────────────────────────────────────

    def _save_formulas(self) -> None:
        """Save the current editor formulas to a TOML file.

        Format::

            version = 1

            [formulas]
            a = '{det/source}["CH00"].mean("time")'
            b = '{a} + 1'
        """
        text = self._editor.toPlainText().strip()
        if not text:
            return
        pairs = parse_named_formulae(text)
        if not pairs:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save formulas', '',
            'TOML files (*.toml);;All files (*)')
        if not path:
            return
        try:
            lines = ['version = 1\n', '\n', '[formulas]\n']
            for name, expr in pairs:
                # TOML literal strings (single-quoted) need no escaping and
                # work perfectly for expressions which only use double-quotes.
                # Fall back to a basic string with escaping if a single quote
                # appears in the expression (extremely rare).
                if "'" not in expr:
                    lines.append(f"{name} = '{expr}'\n")
                else:
                    escaped = expr.replace('\\', '\\\\').replace('"', '\\"')
                    lines.append(f'{name} = "{escaped}"\n')
            with open(path, 'w', encoding='utf-8') as fh:
                fh.writelines(lines)
        except Exception as exc:
            self._output_widget.log(
                f'<span style="color:red"><b>\u2717 Save failed:</b> '
                f'{_html.escape(str(exc))}</span>')

    def _load_formulas(self) -> None:
        """Load formulas from a TOML file into the editor (replaces content)."""
        if self._editor.toPlainText().strip():
            from qtpy.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, 'Load formulas',
                'Loading will replace the current editor content.\n'
                'Unsaved formulas will be lost.  Continue?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        path, _ = QFileDialog.getOpenFileName(
            self, 'Load formulas', '',
            'TOML files (*.toml);;All files (*)')
        if not path:
            return
        try:
            try:
                import tomllib  # stdlib ≥ Python 3.11
            except ImportError:
                try:
                    import tomli as tomllib  # third-party fallback
                except ImportError:
                    raise ImportError(
                        'TOML support requires Python ≥ 3.11 (tomllib) '
                        'or the "tomli" package.')
            with open(path, 'rb') as fh:
                data = tomllib.load(fh)
            formulas: dict = data.get('formulas', {})
            if not formulas:
                return
            text = '\n'.join(f'{name} = {expr}' for name, expr in formulas.items())
            self._editor.setPlainText(text)
        except Exception as exc:
            self._output_widget.log(
                f'<span style="color:red"><b>\u2717 Load failed:</b> '
                f'{_html.escape(str(exc))}</span>')

    # ── Public API ────────────────────────────────────────────────────────────

    def set_h5_loader(self, loader) -> None:
        """Register an on-demand H5 dataset loader.

        Parameters
        ----------
        loader:
            Callable ``(rel_path: str) -> xr.Dataset | None``.  Called by
            ``_run_formula_pairs`` when it encounters a None value in
            ``_h5_ctx`` (i.e. a dataset that hasn't been loaded yet).
            Also forwarded to the editor so that ``_dims_for_context`` can
            resolve dims for unloaded datasets while the user is typing.
        """
        self._h5_loader = loader
        self._editor._h5_loader = loader

    def push_h5_context(self, xr_ctx: dict) -> None:
        """Inject the H5 xarray context dict into the console namespace.

        *xr_ctx* may map names to ``None`` (names-only / lazy mode).  Only
        non-None values are pushed into the IPython kernel namespace; the
        editor autocomplete sees all names regardless.
        """
        self._h5_ctx = xr_ctx
        self._editor.set_context(self._h5_ctx, self._computed)
        if self._km is not None:
            loaded = {k: v for k, v in xr_ctx.items() if v is not None}
            self._km.kernel.shell.user_ns['_xr'].update(loaded)
        self._validate_formulas()

    def push_computed(self, name: str, ds) -> None:
        """Add or update a computed variable in the console namespace."""
        self._computed[name] = ds
        self._editor.update_computed(name, ds)
        if self._km is not None:
            self._km.kernel.shell.user_ns['_xr'][name] = ds

    def update_computed_live(self, name: str, ds) -> None:
        """Refresh a computed variable's data without touching the IPython namespace.

        Called by DataMixerGUI._eval_formulas on every live-sync tick so that
        chained formulas always see the latest result.  The IPython scratchpad
        is intentionally left at the last user-committed state.

        ``_editor._computed`` is the same dict object as ``self._computed``
        (assigned by reference in ``set_context``), so no extra call is needed.
        """
        self._computed[name] = ds

    def remove_computed(self, name: str) -> None:
        """Remove a single computed variable and release its reference."""
        self._computed.pop(name, None)
        self._computed_formulas.pop(name, None)
        self._editor.remove_computed(name)
        if self._km is not None:
            self._km.kernel.shell.user_ns['_xr'].pop(name, None)

    def _validate_formulas(self) -> None:
        """Live-check formula {name} refs and update the toolbar indicator.

        Runs on every keystroke (via textChanged).  Only the parser and a
        set-lookup are called — no H5 I/O or eval — so it is fast.
        """
        if self._validation_label is None:
            return
        text = self._editor.toPlainText().strip()
        if not text:
            self._validation_label.setText('')
            return
        pairs = parse_named_formulae(text)
        if not pairs:
            self._validation_label.setText(
                '<span style="color:#999">no formula</span>')
            return
        available = set(self._h5_ctx.keys()) | set(self._computed.keys())
        errors: list[str] = []
        for name, expr in pairs:
            missing = [r for r in re.findall(r'\{([^}]+)\}', expr)
                       if r not in available]
            if missing:
                errors.append(f'{name}: {", ".join(missing)}')
            available.add(name)   # cascading — later formulas may use this output
        if errors:
            tip = 'Unresolved references:\n' + '\n'.join(errors)
            self._validation_label.setToolTip(tip)
            self._validation_label.setText(
                f'<span style="color:#c87000">⚠ {len(errors)} broken ref(s)</span>')
        else:
            n = len(pairs)
            self._validation_label.setToolTip('')
            self._validation_label.setText(
                f'<span style="color:#1a6b1a">✓ {n} formula(s) ready</span>')

    def recompute_all(self) -> None:
        """Re-run all stored formulas (from ``_computed_formulas``) in order.

        Runs a validation pass first: each formula's ``{name}`` references are
        checked against the H5 context and the formulas that precede it.  The
        output panel shows a per-formula status (✓ ready / ⚠ broken refs)
        before evaluation begins.

        Useful after loading a new H5 file with the same dataset structure.
        """
        pairs = list(self._computed_formulas.items())
        if not pairs:
            self._output_widget.log(
                '<span style="color:#888"><i>\u21ba No stored formulas to recompute.</i></span>')
            return

        # ── Validation pass ───────────────────────────────────────────────────
        available: set = set(self._h5_ctx.keys())
        validation: dict[str, list[str]] = {}
        for name, expr in pairs:
            missing = [
                r for r in re.findall(r'\{([^}]+)\}', expr)
                if r not in available
            ]
            validation[name] = missing
            available.add(name)   # assume it will succeed for downstream deps

        n_broken = sum(1 for m in validation.values() if m)
        status_color = '#c87000' if n_broken else '#1a6b1a'
        self._output_widget.log(
            f'<b>\u21ba Recompute all</b> — '
            f'<span style="color:{status_color}">'
            f'{len(pairs) - n_broken}/{len(pairs)} formula(s) valid</span>')

        for name, missing in validation.items():
            if missing:
                refs = ', '.join(f'<code>{{{_html.escape(r)}}}</code>' for r in missing)
                self._output_widget.log(
                    f'&nbsp;&nbsp;<span style="color:#c87000">'
                    f'\u26a0 <b>{_html.escape(name)}</b>: missing {refs}</span>')
            else:
                self._output_widget.log(
                    f'&nbsp;&nbsp;<span style="color:#1a6b1a">'
                    f'\u2713 <b>{_html.escape(name)}</b></span>')

        if n_broken == len(pairs):
            return   # nothing can run

        # ── Evaluation ───────────────────────────────────────────────────────
        self._run_formula_pairs(pairs)

    def recall_formula(self, name: str) -> None:
        """Append ``name = <formula>`` for *name* to the formula editor.

        Called when the user selects "→ Send formula to editor" from the
        VariableBrowserWidget right-click context menu.
        """
        if name not in self._computed_formulas:
            return
        line = f'{name} = {self._computed_formulas[name]}'
        current = self._editor.toPlainText()
        if current and not current.endswith('\n'):
            line = '\n' + line
        self._editor.appendPlainText(line)
        self._editor.setFocus()

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
