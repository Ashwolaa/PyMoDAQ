"""
toolbar_popup.py
================

:class:`ToolbarPopupTree` — a :class:`~qtpy.QtWidgets.QToolButton` that
reveals a floating :class:`SettingsPanel` anchored below it.

The panel hosts a :class:`~pymodaq_gui.parameter.ParameterTree` scoped to a
single pyqtgraph :class:`~pymodaq_gui.parameter.Parameter` (or sub-group).
Because the tree operates **directly** on the original Parameter object — not
a copy — all edits are immediately live in the canonical settings state.  No
additional synchronisation (widget_sync, blockSignals, …) is required.

The panel uses ``Qt.Tool | Qt.FramelessWindowHint``:

* stays above the main window without appearing in the taskbar
* persists while child dialogs (file browsers, colour pickers) are open,
  unlike a ``Qt.Popup`` which would dismiss on any outside click
* dismissed by re-clicking the toolbar button, or by the panel's own × button

Typical usage
-------------
::

    # Inside a control-module's _bind_toolbar_to_settings():
    save_btn = ToolbarPopupTree(
        self.settings.child('saver_settings'),
        title='Save',
        icon_name='save',
    )
    self.ui.toolbar.addWidget(save_btn)

"""

from __future__ import annotations

from qtpy.QtCore import Qt, QPoint, Signal
from qtpy.QtWidgets import (
    QToolButton, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QWidget,
)

from pymodaq_gui.parameter import ParameterTree


# ---------------------------------------------------------------------------
# Internal: title bar
# ---------------------------------------------------------------------------

class _PanelTitleBar(QWidget):
    """Slim draggable title bar with a close (×) button.

    Dragging the bar repositions the parent :class:`SettingsPanel`.
    """

    close_clicked = Signal()

    _HEIGHT = 22  # px

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(self._HEIGHT)
        self.setAutoFillBackground(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 2, 0)
        layout.setSpacing(0)

        lbl = QLabel(title)
        lbl.setStyleSheet('font-weight: bold; font-size: 11px;')
        layout.addWidget(lbl)
        layout.addStretch()

        close_btn = QPushButton('×')
        close_btn.setFixedSize(18, 18)
        close_btn.setFlat(True)
        close_btn.setStyleSheet('font-size: 14px; padding: 0;')
        close_btn.clicked.connect(self.close_clicked)
        layout.addWidget(close_btn)

        self._drag_pos = None

    # ------------------------------------------------------------------
    # Drag-to-move support
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = (
                event.globalPos() - self.parent().frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self.parent().move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


# ---------------------------------------------------------------------------
# Public: floating settings panel
# ---------------------------------------------------------------------------

class SettingsPanel(QFrame):
    """Floating frameless panel containing a :class:`ParameterTree` slice.

    Parameters
    ----------
    param : Parameter
        The pyqtgraph Parameter sub-group to display.  Shown directly — not
        a copy — so edits are live on the original settings object.
    title : str
        Heading shown in the title bar.
    min_width : int
        Minimum panel width in pixels (default 260).
    """

    closed = Signal()  # emitted when the × button is clicked

    def __init__(
        self,
        param,
        title: str = '',
        min_width: int = 260,
    ):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setMinimumWidth(min_width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 4)
        layout.setSpacing(0)

        self._title_bar = _PanelTitleBar(title, parent=self)
        self._title_bar.close_clicked.connect(self._on_close)
        layout.addWidget(self._title_bar)

        self._tree = ParameterTree(parent=self, showHeader=False)
        # Ensure the group is expanded: pyqtgraph's showTop=False creates a
        # 1×1 hidden wrapper item whose children are only visible when the
        # item is expanded.  A group with expanded=False would appear empty.
        param.setOpts(expanded=True)
        self._tree.setParameters(param, showTop=False)
        # self._tree.setMinimumHeight(150)
        self._tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._tree)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def show_below(self, widget: QWidget) -> None:
        """Position the panel directly below *widget* and show it."""
        pos = widget.mapToGlobal(QPoint(0, widget.height()))
        self.move(pos)
        self.show()
        self.adjustSize()  # compute size after layout is live
        self.raise_()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_close(self):
        self.hide()
        self.closed.emit()


# ---------------------------------------------------------------------------
# Public: toolbar button
# ---------------------------------------------------------------------------

class ToolbarPopupTree(QToolButton):
    """A :class:`~qtpy.QtWidgets.QToolButton` that toggles a floating
    :class:`SettingsPanel`.

    Click once to open the panel anchored below the button; click again (or
    press × in the panel) to close it.  Because the panel's
    :class:`ParameterTree` operates directly on *param*, no widget_sync
    bindings are needed for the popup content.

    Parameters
    ----------
    param : Parameter
        The pyqtgraph Parameter (or sub-group) to display in the panel.
    title : str
        Label on the button and heading inside the panel.
    icon_name : str, optional
        Icon name accepted by :func:`pymodaq_gui.utils.styling.create_icon`.
    min_width : int
        Minimum width of the popup panel (default 260 px).
    parent : QWidget, optional
    """

    def __init__(
        self,
        param,
        title: str = '',
        icon_name: str = '',
        min_width: int = 260,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self._panel = SettingsPanel(param, title=title, min_width=min_width)
        self._panel.closed.connect(lambda: self.setChecked(False))

        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        if title:
            self.setText(f'{title} ▾')
            self.setToolTip(f'Open {title} settings panel')

        if icon_name:
            from pymodaq_gui.utils.styling import create_icon
            self.setIcon(create_icon(icon_name))

        self.toggled.connect(self._on_toggled)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_toggled(self, checked: bool):
        if checked:
            self._panel.show_below(self)
        else:
            self._panel.hide()
