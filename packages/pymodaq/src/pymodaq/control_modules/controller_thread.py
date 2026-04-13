"""One-thread-per-controller: ControllerThread serialises all hardware access.

One ``ControllerThread`` instance lives inside a dedicated ``QThread``.
Qt's queued-connection mechanism serialises concurrent slot calls automatically
— no additional locking is required.

Design
------
One physical hardware device → one ``ControllerThread`` → one plugin instance.
DAQ_Move and DAQ_Viewer are lightweight GUI subscribers that connect to this
thread's signals; they never touch the SDK directly.

Acquisition modes
-----------------
**Pull (software-polled)**
    Each DAQ subscriber drives its own timer in the GUI thread.  On each tick
    it calls ``request_read(channel, fresh=True)`` which polls the hardware and
    updates the plugin's internal cache.  Between ticks, any caller can call
    ``request_read(channel, fresh=False)`` to get the last cached value
    immediately without a hardware round-trip.

**Push (hardware-driven)**
    The plugin has its own acquisition loop started via ``start_acquisition``.
    When new data arrives the plugin emits ``new_data(DataToExport)``;
    ``ControllerThread`` fans it out as ``data_ready`` per channel.
    No timer is needed on the controller side.

New-style plugin interface (QObject)
-------------------------------------
    def open(self, settings) -> None
    def close(self) -> None
    def start_acquisition(self, names: list[str]) -> None   # optional
    def stop_acquisition(self) -> None                      # optional
    def query_data(self, names=None, fresh=True) -> DataToExport
    def change_to(self, name: str, value) -> None
    def commit_settings(self, path, data, change) -> None   # optional
    new_data = Signal(object)                               # optional (push mode)

Legacy plugins
--------------
``DAQ_Move_base`` and ``DAQ_Viewer_base`` plugins continue to work via the
master/slave mechanism until migrated.  See ``PLUGIN_MIGRATION_GUIDE.md``.
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
        self._settings_ref = settings               # GUI-thread Parameter, read-only here
        self._plugin: Any = None                   # single plugin instance
        self._grab_timers: dict[str, QTimer] = {}  # channel → QTimer (pull mode)
        self._subscribed_channels: set[str] = set()

    # ── Slots ← GUI thread ───────────────────────────────────────────────────

    @Slot()
    def ini_hardware(self) -> None:
        """Instantiate the plugin, open hardware, emit capabilities + status."""
        try:
            plugin = self._plugin_class()
            plugin.open(self._settings_ref)
            self._plugin = plugin

            # Wire push-mode signal if the plugin supports it
            new_data = getattr(plugin, 'new_data', None)
            if new_data is not None:
                new_data.connect(self._on_plugin_new_data)

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
        self._subscribed_channels.clear()

        if self._plugin is not None:
            stop = getattr(self._plugin, 'stop_acquisition', None)
            if stop is not None:
                try:
                    stop()
                except Exception:
                    pass
            try:
                self._plugin.close()
            except Exception:
                pass
            self._plugin = None

        self.hardware_status.emit(False, 'Closed')

    @Slot(str)
    @Slot(str, bool)
    def request_read(self, channel: str, fresh: bool = True) -> None:
        """Read *channel* and emit ``data_ready(channel, dte)``.

        Parameters
        ----------
        channel :
            Channel name (must match a name in plugin ``Capabilities``).
        fresh :
            ``True``  — poll the hardware now and update the plugin's cache.
            ``False`` — return the last cached value without a hardware call.
                        Use this for fast display rates between grab ticks.
        """
        if self._plugin is None:
            return
        try:
            dte = self._plugin.query_data(names=[channel], fresh=fresh)
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
        """Subscribe *channel* and start its periodic grab timer.

        Registers *channel* in ``_subscribed_channels`` and notifies the plugin
        via ``start_acquisition`` (push-mode plugins) or starts a ``QTimer``
        (pull-mode plugins).

        ``QTimer`` is created here, inside a slot, so it is affiliated with the
        hardware thread's event loop (CR-7).
        """
        self._subscribed_channels.add(channel)
        self._notify_plugin_subscriptions()

        # Pull-mode timer (no-op for push-mode plugins that use new_data signal)
        self.stop_grab(channel)   # replace any existing timer
        timer = QTimer(self)
        timer.setInterval(int(period_ms))
        timer.timeout.connect(lambda: self.request_read(channel, True))
        timer.start()
        self._grab_timers[channel] = timer

    @Slot(str)
    def stop_grab(self, channel: str) -> None:
        """Unsubscribe *channel* and stop its grab timer.

        Notifies the plugin via ``stop_acquisition`` when no channels remain
        subscribed.
        """
        timer = self._grab_timers.pop(channel, None)
        if timer is not None:
            timer.stop()

        self._subscribed_channels.discard(channel)
        if not self._subscribed_channels:
            stop = getattr(self._plugin, 'stop_acquisition', None) if self._plugin else None
            if stop is not None:
                try:
                    stop()
                except Exception:
                    pass
        else:
            self._notify_plugin_subscriptions()

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

    # ── Internal ─────────────────────────────────────────────────────────────

    def _notify_plugin_subscriptions(self) -> None:
        """Tell the plugin which channels are currently subscribed."""
        if self._plugin is None:
            return
        start = getattr(self._plugin, 'start_acquisition', None)
        if start is not None:
            try:
                start(list(self._subscribed_channels))
            except Exception:
                pass

    def _on_plugin_new_data(self, dte: object) -> None:
        """Fan out a push-mode DataToExport to per-channel ``data_ready`` signals."""
        data_list = getattr(dte, 'data', [])
        for dwa in data_list:
            channel = getattr(dwa, 'name', None)
            if channel is not None:
                self.data_ready.emit(channel, dte)
