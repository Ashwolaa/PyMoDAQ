"""ActorGrabStatusWidget — compact read-only widget showing actor acquisition state.

Displayed in director settings panels.  Updated by the ``on_acquisition_status``
RPC callback; all connected directors show identical content.

Example display::

    ┌─ Actor acquisition state ─────────────────────────────┐
    │  ● GRABBING                                           │
    │  frame     @ 10.0 Hz  ← localhost.det_dir_1          │
    │  position  @ 20.0 Hz  ← localhost.move_dir_1         │
    └───────────────────────────────────────────────────────┘
"""
from __future__ import annotations

from typing import Optional

from qtpy.QtWidgets import QGroupBox, QFormLayout, QLabel, QVBoxLayout, QWidget


class ActorGrabStatusWidget(QWidget):
    """Read-only widget that mirrors the actor's current acquisition state.

    Parameters
    ----------
    parent:
        Optional Qt parent widget.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._group = QGroupBox("Actor acquisition state")
        self._form = QFormLayout(self._group)
        self._form.setContentsMargins(4, 4, 4, 4)

        self._status_label = QLabel("IDLE")
        self._form.addRow("Status:", self._status_label)

        layout.addWidget(self._group)
        self._channel_rows: list[tuple[QLabel, QLabel]] = []

    def update(self, status: dict) -> None:
        """Update the widget from an ``on_acquisition_status`` payload.

        Parameters
        ----------
        status:
            Dict with keys ``"read_list"`` (dict) and ``"is_grabbing"`` (bool).
        """
        is_grabbing: bool = status.get("is_grabbing", False)
        read_list: dict = status.get("read_list") or {}

        # Remove old channel rows.
        for name_lbl, info_lbl in self._channel_rows:
            self._form.removeRow(name_lbl)
        self._channel_rows.clear()

        if is_grabbing:
            self._status_label.setText("● GRABBING")
            for channel_key, info in read_list.items():
                period = info.get("period", 0)
                hz = f"{1.0 / period:.1f} Hz" if period and period > 0 else "max Hz"
                requester = info.get("requester") or ""
                info_text = f"@ {hz}  ← {requester}" if requester else f"@ {hz}"
                name_lbl = QLabel(channel_key)
                info_lbl = QLabel(info_text)
                self._form.addRow(name_lbl, info_lbl)
                self._channel_rows.append((name_lbl, info_lbl))
        else:
            self._status_label.setText("IDLE")
