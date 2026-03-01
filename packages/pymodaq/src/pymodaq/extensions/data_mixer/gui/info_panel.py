"""Info panel widget for the DataMixer GUI.

Shows a rich HTML summary of the selected dataset or computed variable.
"""
from __future__ import annotations

import html as _html
from typing import Optional

from qtpy.QtGui import QPalette
from qtpy.QtWidgets import QWidget, QVBoxLayout, QTextEdit

from pymodaq.extensions.data_mixer.gui.formatters import _format_xr_html


class InfoPanelWidget(QWidget):
    """Read-only HTML panel showing info about the selected dataset.

    Updated by calling :meth:`display` when the variable browser emits
    ``item_selected_sig``.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setAcceptRichText(True)
        layout.addWidget(self._text)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _palette_colors(self) -> dict:
        """Derive HTML-safe colours from the widget's current palette.

        Returns a dict suitable for passing to :func:`_format_xr_html`.
        All colours adapt automatically to light / dark themes.
        """
        p = self._text.palette()
        text = p.color(QPalette.ColorRole.Text)
        window = p.color(QPalette.ColorRole.Window)
        highlight = p.color(QPalette.ColorRole.Highlight)
        # A "dim" colour sits midway between text and window — visible on
        # both white and dark backgrounds without being as harsh as the
        # full text colour.
        dim = '#{:02x}{:02x}{:02x}'.format(
            (text.red()   + window.red())   // 2,
            (text.green() + window.green()) // 2,
            (text.blue()  + window.blue())  // 2,
        )
        return {
            'dim':     dim,
            'type':    highlight.name(),
            'dataset': highlight.name(),
            'lazy':    highlight.name(),
        }

    # ── public API ────────────────────────────────────────────────────────────

    def display(self, ds_name: str, ds, source: str = 'H5',
                formula: Optional[str] = None, var_name: str = '') -> None:
        """Render info for *ds* (an xr.Dataset).

        Parameters
        ----------
        ds_name:
            Key used to reference this dataset (e.g. ``'test/Mock2D_0'``).
        ds:
            The ``xr.Dataset`` to display.
        source:
            ``'H5'`` or ``'Computed'``.
        formula:
            If *source* is ``'Computed'``, the formula that produced this var.
        var_name:
            If non-empty, highlight the given variable (leaf selected).
        """
        if ds is None:
            self.clear()
            return

        try:
            colors = self._palette_colors()
            badge_color = colors['dataset'] if source == 'Computed' else colors['dim']
            badge = (f'<span style="color:{badge_color}; font-weight:bold">'
                     f'xr.Dataset</span> &nbsp;·&nbsp; '
                     f'<b>{_html.escape(ds_name)}</b> '
                     f'[{_html.escape(source)}]')

            html_parts = [badge]

            if formula:
                html_parts.append(
                    f'<br><span style="color:{colors["dim"]}">Formula:</span> '
                    f'<code>{_html.escape(formula)}</code>')

            html_parts.append('<br>' + _format_xr_html(ds, ds_name, colors=colors))

            if var_name:
                try:
                    var = ds[var_name]
                    dims_str = ', '.join(str(d) for d in var.dims)
                    vals = var.values
                    if vals.size > 0:
                        stats = (f'min=<b>{float(vals.min()):.4g}</b>'
                                 f'  max=<b>{float(vals.max()):.4g}</b>'
                                 f'  mean=<b>{float(vals.mean()):.4g}</b>')
                    else:
                        stats = '(empty)'
                    html_parts.append(
                        f'<br><b>Selected variable:</b> '
                        f'<code>{_html.escape(var_name)}</code> '
                        f'({dims_str}) {var.dtype}  {stats}')
                except Exception:
                    pass

            self._text.setHtml('<br>'.join(html_parts))
        except Exception as exc:
            self._text.setPlainText(f'[display error] {exc}')

    def clear(self) -> None:
        """Clear the info panel."""
        self._text.clear()
