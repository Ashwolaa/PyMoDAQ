"""One-thread-per-controller: ControllerThread serialises all hardware access.

One ``ControllerThread`` instance lives inside a dedicated ``QThread``.
Qt's queued-connection mechanism serialises concurrent slot calls automatically
— no additional locking is required.

New-style plugin interface
--------------------------
Plugins must implement:

    def open(self, settings, controller=None) -> Any:
        \"\"\"Open hardware.

        *controller* is ``None`` on the first call.  When a second plugin
        class sharing the same ``hardware_class`` is initialised, the already-
        open SDK object is passed in so the plugin can reuse the connection.

        Return the SDK / controller object (or ``None`` for stateless plugins).
        \"\"\"

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

Old-style adapters (Phase 4)
----------------------------
``DAQ_Move_base`` and ``DAQ_Viewer_base`` expose ``query_data`` / ``change_to``
wrappers around the legacy ``get_actuator_value`` / ``move_abs`` / ``grab_data``
interface.  Those adapters are wired up in Phase 4; this file is intentionally
new-style only.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from qtpy.QtCore import QObject, Signal, Slot, QTimer

if TYPE_CHECKING:
    from pymodaq_gui.parameter import Parameter

__all__ = ['ControllerThread']


class ControllerThread(QObject):
    """QObject that lives in a dedicated QThread and owns the plugin + hardware.

    In production, instantiate via :class:`~pymodaq.control_modules.controller_registry.ControllerRegistry`
    which handles ``moveToThread`` and ``QThread`` lifecycle.

    Signals fire on the GUI thread via Qt's cross-thread queued delivery.
    Slots execute in the hardware thread's event loop.
    """

    # ── Signals → GUI thread ─────────────────────────────────────────────────
    data_ready          = Signal(str, object)        # (channel, DataToExport)
    change_done         = Signal(str, object)        # (channel, value)
    hardware_status     = Signal(bool, str)          # (connected, info)
    settings_changed    = Signal(list, object, str)  # (path, data, change)  emitted by plugin
    capabilities_signal = Signal(object)             # Capabilities

    def __init__(self, plugin_class: type, settings: 'Parameter') -> None:
        super().__init__()
        self._plugin_class = plugin_class
        self._settings_ref = settings           # GUI-thread Parameter, read-only here
        self._plugins: dict[type, Any] = {}    # plugin_class → plugin instance
        self._controller: Any = None           # shared SDK object set by first ini_hardware
        self._grab_timers: dict[str, QTimer] = {}

    # ── Slots ← GUI thread ───────────────────────────────────────────────────

    @Slot()
    def ini_hardware(self) -> None:
        """Instantiate the plugin class, open hardware, emit capabilities + status.

        If a second plugin class sharing the same ``hardware_class`` calls this
        slot (via a second ``acquire``), the already-open ``self._controller``
        SDK object is passed in so the plugin can reuse the connection without
        reopening hardware.
        """
        try:
            plugin = self._plugin_class()
            controller = plugin.open(self._settings_ref, controller=self._controller)
            if self._controller is None and controller is not None:
                self._controller = controller
            self._plugins[self._plugin_class] = plugin

            caps = getattr(plugin, 'capabilities', None)
            if caps is not None:
                self.capabilities_signal.emit(caps)

            self.hardware_status.emit(True, f'{self._plugin_class.__name__} connected')
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot()
    def close_hardware(self) -> None:
        """Stop all grab timers, close all plugin instances, reset state."""
        for timer in list(self._grab_timers.values()):
            timer.stop()
        self._grab_timers.clear()

        for plugin in list(self._plugins.values()):
            try:
                plugin.close()
            except Exception:
                pass
        self._plugins.clear()
        self._controller = None
        self.hardware_status.emit(False, 'Closed')

    @Slot(str)
    def request_read(self, channel: str) -> None:
        """One-shot read on *channel*; emits ``data_ready(channel, dte)``."""
        plugin = self._plugin_for_channel(channel)
        if plugin is None:
            return
        try:
            dte = plugin.query_data(names=[channel], fresh=True)
            self.data_ready.emit(channel, dte)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, object)
    def request_write(self, channel: str, value: object) -> None:
        """Write *value* to *channel*; emits ``change_done(channel, value)``."""
        plugin = self._plugin_for_channel(channel)
        if plugin is None:
            return
        try:
            plugin.change_to(channel, value)
            self.change_done.emit(channel, value)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, float)
    def start_grab(self, channel: str, period_ms: float) -> None:
        """Start (or restart) periodic reads on *channel* every *period_ms* ms.

        ``QTimer`` is created here, inside a slot, so it is affiliated with the
        hardware thread's event loop (see CR-7).
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
        """Relay a GUI parameter edit to all plugin instances."""
        for plugin in self._plugins.values():
            commit = getattr(plugin, 'commit_settings', None)
            if commit is not None:
                try:
                    commit(path, data, change)
                except Exception:
                    pass

    # ── Internal ─────────────────────────────────────────────────────────────

    def _plugin_for_channel(self, channel: str) -> Any | None:
        """Return the plugin instance that owns *channel*, or ``None``.

        With a single plugin, dispatching is trivial.  With multiple plugins
        (legacy mixed DAQ_Move + DAQ_Viewer case), each plugin's
        ``Capabilities`` is checked for the channel name.
        """
        if not self._plugins:
            return None
        if len(self._plugins) == 1:
            return next(iter(self._plugins.values()))
        for plugin in self._plugins.values():
            caps = getattr(plugin, 'capabilities', None)
            if caps is None:
                continue
            names = (
                [v.name for v in getattr(caps, 'variables', [])]
                + [o.name for o in getattr(caps, 'observables', [])]
            )
            if channel in names:
                return plugin
        return None
