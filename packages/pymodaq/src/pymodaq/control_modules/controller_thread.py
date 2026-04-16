"""One-thread-per-controller: ControllerThread serialises all hardware access.

One ``ControllerThread`` instance lives inside a dedicated ``QThread``.
Qt's queued-connection mechanism serialises concurrent slot calls automatically
— no additional locking is required.

Design
------
One physical hardware device → one ``ControllerThread`` → one plugin instance.
DAQ_Move and DAQ_Viewer are lightweight GUI subscribers that connect to this
thread's signals; they never touch the SDK directly.

Channel convention
------------------
Each DAQ sets a *channel* name equal to ``plugin.axis_name`` (multi-axis
plugins) or an empty string (single-axis plugins, broadcast).

``change_done`` and ``data_ready`` carry the channel name so each DAQ_Move /
DAQ_Viewer can filter to its own channel::

    def _on_change_done(self, channel, value):
        if channel and channel != self._channel:
            return          # not for me
        ...

An empty channel means "broadcast": all connected subscribers receive it.

Old-style plugin support
------------------------
Plugins that subclass ``DAQ_Move_base`` / ``DAQ_Viewer_base`` are fully
supported.  ``ControllerThread`` calls the old API (``ini_stage``,
``move_abs``, ``poll_moving``, ``grab_data``) and bridges the plugin's
async-completion signals (``move_done_signal``, ``dte_signal``) to the clean
``change_done`` / ``data_ready`` signals.

New-style plugin interface (future)
-------------------------------------
    def open(self, settings) -> None
    def close(self) -> None
    def query_data(self, names=None, fresh=True) -> DataToExport
    def change_to(self, name: str, value) -> None
    def commit_settings(self, path, data, change) -> None   # optional
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from qtpy.QtCore import QObject, Signal, Slot, QTimer

from pymodaq_utils.utils import ThreadCommand

if TYPE_CHECKING:
    from pymodaq_gui.parameter import Parameter

__all__ = ['ControllerThread']


# ---------------------------------------------------------------------------
# Plugin parent shim
# ---------------------------------------------------------------------------

class _StatusSig:
    """Minimal status_sig duck-type so old plugins can call parent.status_sig.emit()."""

    def __init__(self, ct: 'ControllerThread') -> None:
        self._ct = ct

    def emit(self, cmd: ThreadCommand) -> None:
        # Forward text status updates to the clean signal; ignore the rest
        # (move completion goes through move_done_signal, not here).
        attr = cmd.attribute
        if isinstance(attr, str):
            self._ct.status_message.emit(attr)
        elif isinstance(attr, (list, tuple)) and attr:
            self._ct.status_message.emit(str(attr[0]))
        elif attr is not None:
            self._ct.status_message.emit(str(attr))


class _PluginParentShim:
    """Minimal parent object that old-style plugins expect.

    Old plugins do ``self.parent.status_sig.emit(ThreadCommand(...))`` and
    ``self.parent.title``.  This shim satisfies both without introducing
    the full Worker hierarchy.
    """

    def __init__(self, ct: 'ControllerThread', title: str) -> None:
        self.title = title
        self.status_sig = _StatusSig(ct)


# ---------------------------------------------------------------------------
# ControllerThread
# ---------------------------------------------------------------------------

class ControllerThread(QObject):
    """QObject that lives in a dedicated QThread and owns the plugin + hardware.

    In production, instantiate via
    :class:`~pymodaq.control_modules.controller_registry.ControllerRegistry`
    which handles ``moveToThread`` and ``QThread`` lifecycle.

    Signals fire in the GUI thread via Qt's cross-thread queued delivery.
    Slots execute in the hardware thread's event loop.
    """

    # ── Signals → GUI thread ─────────────────────────────────────────────────
    data_ready          = Signal(str, object)        # (channel, DataToExport)
    change_done         = Signal(str, object)        # (channel, DataActuator)
    hardware_status     = Signal(bool, str)          # (connected, info)
    status_message      = Signal(str)                # text for DAQ status bars
    settings_changed    = Signal(list, object, str)  # (path, data, change)
    capabilities_signal = Signal(object)             # Capabilities

    def __init__(self, plugin_class: type, settings: 'Parameter') -> None:
        super().__init__()
        self._plugin_class = plugin_class
        self._settings_ref = settings           # shared hw_settings (GUI thread)
        self._plugin: Any = None
        self._controller: Any = None            # shared SDK object
        self._grab_timers: dict[str, QTimer] = {}
        self._pending_channel: str = ''         # channel of in-flight move

    # ── Slots ← GUI thread ───────────────────────────────────────────────────

    @Slot()
    def ini_hardware(self) -> None:
        """Instantiate the plugin, open hardware, emit capabilities + status.

        Supports both old-style (``ini_stage`` / ``ini_detector``) and
        new-style (``open``) plugin interfaces.
        """
        try:
            if self._is_new_style():
                self._ini_new_style()
            else:
                self._ini_old_style_actuator()
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

        self._controller = None
        self.hardware_status.emit(False, 'Closed')

    @Slot(str)
    @Slot(str, bool)
    def request_read(self, channel: str, fresh: bool = True) -> None:
        """Read *channel* and emit ``data_ready(channel, dte)``.

        For old-style actuators: calls ``get_actuator_value`` and wraps
        the result in a DataToExport.
        For new-style plugins: calls ``query_data``.
        """
        if self._plugin is None:
            return
        try:
            if self._is_new_style():
                dte = self._plugin.query_data(names=[channel], fresh=fresh)
                self.data_ready.emit(channel, dte)
            else:
                self._read_old_style_actuator(channel)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, object)
    def request_write(self, channel: str, value: object) -> None:
        """Write *value* to *channel*.

        For old-style actuators: sets axis, calls ``move_abs`` /
        ``move_home``, starts ``poll_moving`` timer.  ``change_done`` is
        emitted when ``move_done_signal`` fires.

        For new-style plugins: calls ``change_to`` and emits
        ``change_done`` immediately.
        """
        if self._plugin is None:
            return
        try:
            if self._is_new_style():
                self._plugin.change_to(channel, value)
                self.change_done.emit(channel, value)
            else:
                self._write_old_style_actuator(channel, value)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, float)
    def start_grab(self, channel: str, period_ms: float) -> None:
        """Start a periodic read timer for *channel* (pull-mode grab).

        Created inside a slot so the QTimer is affiliated with the
        hardware thread's event loop.
        """
        self.stop_grab(channel)
        timer = QTimer(self)
        timer.setInterval(int(period_ms))
        timer.timeout.connect(lambda: self.request_read(channel, True))
        timer.start()
        self._grab_timers[channel] = timer

    @Slot(str)
    def stop_grab(self, channel: str) -> None:
        """Stop and remove the grab timer for *channel*."""
        timer = self._grab_timers.pop(channel, None)
        if timer is not None:
            timer.stop()

    @Slot(list, object, str)
    def update_settings(self, path: list, data: object, change: str) -> None:
        """Relay a GUI hw_settings edit to the plugin's commit_settings(param).

        All plugins (old-style and new-style) use the same signature:
        ``commit_settings(param: Parameter)``.  We look up the Parameter
        node from the shared hw_settings using *path* and pass it through.
        """
        if self._plugin is None:
            return
        commit = getattr(self._plugin, 'commit_settings', None)
        if commit is None:
            return
        try:
            param = self._settings_ref.child(*path) if path else self._settings_ref
            commit(param)
        except Exception:
            pass

    # ── Internal: new-style plugin ────────────────────────────────────────────

    def _is_new_style(self) -> bool:
        """Return True if the plugin uses the new open/query_data/change_to API.

        Detection: old-style plugins always declare ``ini_stage`` somewhere in
        their class hierarchy (inherited from ``DAQ_Move_base``).  New-style
        plugins do not.  We check the class (or the instantiated plugin) rather
        than looking for ``open``, since ``open`` is a Python builtin and could
        appear for unrelated reasons.
        """
        obj = self._plugin if self._plugin is not None else self._plugin_class
        return not hasattr(obj, 'ini_stage')

    def _ini_new_style(self) -> None:
        plugin = self._plugin_class()
        plugin.open(self._settings_ref)
        self._plugin = plugin

        new_data = getattr(plugin, 'new_data', None)
        if new_data is not None:
            new_data.connect(self._on_plugin_new_data)

        caps = getattr(plugin, 'capabilities', None)
        if caps is not None:
            self.capabilities_signal.emit(caps)

        self.hardware_status.emit(True, f'{self._plugin_class.__name__} connected')

    # ── Internal: old-style actuator ─────────────────────────────────────────

    def _ini_old_style_actuator(self) -> None:
        """Initialise an old-style DAQ_Move_base plugin."""
        shim = _PluginParentShim(self, self._plugin_class.__name__)
        plugin = self._plugin_class(
            parent=shim,
            params_state=self._settings_ref.saveState(),
        )
        info, initialized = plugin.ini_stage(self._controller)
        if not initialized:
            self.hardware_status.emit(False, str(info))
            return
        self._controller = plugin.controller   # store for subsequent plugins
        self._plugin = plugin
        plugin.move_done_signal.connect(self._on_move_done)
        self.hardware_status.emit(True, str(info))

    def _read_old_style_actuator(self, channel: str) -> None:
        """One-shot position read for an old-style actuator plugin.

        Emits the raw return value of ``get_actuator_value``.  The receiver
        (``DAQ_Move._on_data_ready``) normalises it via ``_check_data_type``.
        """
        if channel and hasattr(self._plugin, 'axis_name'):
            if self._plugin.axis_name != channel:
                self._plugin.axis_name = channel
        pos = self._plugin.get_actuator_value()
        self.data_ready.emit(channel, pos)

    def _write_old_style_actuator(self, channel: str, value: object) -> None:
        """Move an old-style actuator plugin to *value* on *channel*."""
        if channel and hasattr(self._plugin, 'axis_name'):
            if self._plugin.axis_name != channel:
                self._plugin.axis_name = channel
        self._pending_channel = channel
        self._plugin.move_is_done = False
        if value == 'home':
            self._plugin.move_home()
        else:
            self._plugin.move_abs(value)
        self._plugin.poll_moving()   # starts QTimer, returns immediately

    @Slot(object)  # DataActuator
    def _on_move_done(self, data_actuator: object) -> None:
        """Receive move completion from the plugin; emit change_done."""
        channel = self._pending_channel
        self._pending_channel = ''
        self.change_done.emit(channel, data_actuator)

    # ── Internal: new-style push mode ────────────────────────────────────────

    def _on_plugin_new_data(self, dte: object) -> None:
        """Fan out a push-mode DataToExport to per-channel data_ready signals."""
        for dwa in getattr(dte, 'data', []):
            channel = getattr(dwa, 'name', None)
            if channel is not None:
                self.data_ready.emit(channel, dte)
