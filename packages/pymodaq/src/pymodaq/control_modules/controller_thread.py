"""One-thread-per-controller: ControllerThread serialises all hardware access.

One ``ControllerThread`` instance lives inside a dedicated ``QThread``.
Qt's queued-connection mechanism serialises concurrent slot calls automatically
— no additional locking is required.

Design
------
One physical hardware device → one ``ControllerThread`` → one plugin instance.
DAQ_Move and DAQ_Viewer are lightweight GUI subscribers that connect to this
thread's signals; they never touch the SDK directly.

New-style plugin interface
--------------------------
Plugins must implement:

    def open(self, settings) -> None:
        \"\"\"Open hardware.  Raise on failure.\"\"\"

    def close(self) -> None:
        \"\"\"Close hardware gracefully.\"\"\"

    def query_data(self, names: list[str] | None = None, fresh: bool = True):
        \"\"\"Read one or more channels; return a DataToExport.\"\"\"

    def change_to(self, name: str, value) -> None:
        \"\"\"Write *value* to channel *name*.\"\"\"

    @property
    def capabilities(self) -> Capabilities | None:
        \"\"\"Declare axes and observables (return None if not supported).\"\"\"

    def commit_settings(self, path: list, data, change: str) -> None:
        \"\"\"React to a GUI parameter edit (optional).\"\"\"

Legacy plugins
--------------
``DAQ_Move_base`` and ``DAQ_Viewer_base`` plugins continue to work unchanged
via the master/slave mechanism until they are migrated.  See
``PLUGIN_MIGRATION_GUIDE.md`` for step-by-step instructions.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from qtpy.QtCore import QObject, Signal, Slot, QTimer

if TYPE_CHECKING:
    from pymodaq_gui.parameter import Parameter

__all__ = ['ControllerThread']


class ControllerThread(QObject):
    """QObject that lives in a dedicated QThread and owns the plugin + hardware.

    In production, instantiate via
    :class:`~pymodaq.control_modules.controller_registry.ControllerRegistry`
    which handles ``moveToThread`` and ``QThread`` lifecycle.

    Signals fire on the GUI thread via Qt's cross-thread queued delivery.
    Slots execute in the hardware thread's event loop.
    """

    # ── Signals → GUI thread ─────────────────────────────────────────────────
    data_ready          = Signal(str, object)        # (channel, DataToExport)
    change_done         = Signal(str, object)        # (channel, value)
    hardware_status     = Signal(bool, str)          # (connected, info)
    settings_changed    = Signal(list, object, str)  # (path, data, change)
    capabilities_signal = Signal(object)             # Capabilities

    def __init__(self, plugin_class: type, settings: 'Parameter') -> None:
        super().__init__()
        self._plugin_class = plugin_class
        self._settings_ref = settings           # GUI-thread Parameter, read-only here
        self._plugin: Any = None               # single plugin instance
        self._grab_timers: dict[str, QTimer] = {}

    # ── Slots ← GUI thread ───────────────────────────────────────────────────

    @Slot()
    def ini_hardware(self) -> None:
        """Instantiate the plugin, open hardware, emit capabilities + status."""
        try:
            plugin = self._plugin_class()
            plugin.open(self._settings_ref)
            self._plugin = plugin

            caps = getattr(plugin, 'capabilities', None)
            if caps is not None:
                self.capabilities_signal.emit(caps)

            self.hardware_status.emit(True, f'{self._plugin_class.__name__} connected')
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot()
    def close_hardware(self) -> None:
        """Stop all grab timers, close the plugin, reset state."""
        for timer in list(self._grab_timers.values()):
            timer.stop()
        self._grab_timers.clear()

        if self._plugin is not None:
            try:
                self._plugin.close()
            except Exception:
                pass
            self._plugin = None

        self.hardware_status.emit(False, 'Closed')

    @Slot(str)
    def request_read(self, channel: str) -> None:
        """One-shot read on *channel*; emits ``data_ready(channel, dte)``."""
        if self._plugin is None:
            return
        try:
            dte = self._plugin.query_data(names=[channel], fresh=True)
            self.data_ready.emit(channel, dte)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, object)
    def request_write(self, channel: str, value: object) -> None:
        """Write *value* to *channel*; emits ``change_done(channel, value)``."""
        if self._plugin is None:
            return
        try:
            self._plugin.change_to(channel, value)
            self.change_done.emit(channel, value)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, float)
    def start_grab(self, channel: str, period_ms: float) -> None:
        """Start (or restart) periodic reads on *channel* every *period_ms* ms.

        ``QTimer`` is created here, inside a slot, so it is affiliated with the
        hardware thread's event loop (see CR-7 in ``CONTROLLER_THREAD_PLAN.md``).
        """
        self.stop_grab(channel)
        timer = QTimer(self)
        timer.setInterval(int(period_ms))
        timer.timeout.connect(lambda: self.request_read(channel))
        timer.start()
        self._grab_timers[channel] = timer

    @Slot(str)
    def stop_grab(self, channel: str) -> None:
        """Stop the grab timer for *channel* (no-op if not running)."""
        timer = self._grab_timers.pop(channel, None)
        if timer is not None:
            timer.stop()

    @Slot(list, object, str)
    def update_settings(self, path: list, data: object, change: str) -> None:
        """Relay a GUI parameter edit to the plugin."""
        if self._plugin is None:
            return
        commit = getattr(self._plugin, 'commit_settings', None)
        if commit is not None:
            try:
                commit(path, data, change)
            except Exception:
                pass
