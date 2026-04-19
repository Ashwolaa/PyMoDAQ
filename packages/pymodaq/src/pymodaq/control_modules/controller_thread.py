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

from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

from qtpy.QtCore import QObject, Signal, Slot, QTimer

from pymodaq_utils.utils import ThreadCommand

if TYPE_CHECKING:
    from pymodaq_gui.parameter import Parameter
    from pymodaq.control_modules.move_utility_classes import DataActuatorType

__all__ = ['ControllerThread', 'ControlCommand']

@dataclass
class _ChannelState:
    """Subscriber tracking for one polled channel.

    ``period_ms`` is the minimum period requested across all subscribers —
    fastest-subscriber-wins policy.  The rate is not raised back when the
    fastest subscriber leaves; a slightly-too-fast timer is harmless.
    """
    sub_count: int = 0
    period_ms: float = 0.0

    def subscribe(self, period_ms: float) -> None:
        self.sub_count += 1
        if self.period_ms == 0.0 or period_ms < self.period_ms:
            self.period_ms = period_ms

    def unsubscribe(self) -> bool:
        """Decrement count; return True when the last subscriber leaves."""
        self.sub_count = max(0, self.sub_count - 1)
        return self.sub_count == 0


@dataclass
class _ReadGroup:
    """One independently-timed hardware read group.

    All channels in the group share a single QTimer.  One hardware transaction
    per tick fans out to all subscribers of every channel in the group.

    Typical usage
    -------------
    - ``group=''``   (default) — the implicit shared group; covers the common
      single-plugin case and multi-axis actuators that read all axes at once.
    - ``group='detector'`` — separate timer for the detector side of a combined
      (actuator + detector) plugin so a slow camera grab has its own cadence.
    - ``group=None`` — solo: each channel gets its own independent QTimer
      (handled outside this dataclass, in ``_solo``).

    Note: grab serialisation (preventing overlapping grab_data calls) is
    handled by the CT-level ``_grab_in_flight`` flag, not per-group.
    ``_pending_group`` on the CT records which group triggered the current
    grab so ``_on_detector_data_ready`` can fan out to the right channels.
    """
    channels: dict  # str → _ChannelState; plain dict avoids dataclass field issues
    timer: Any = None           # QTimer | None

    @property
    def period_ms(self) -> float:
        return min(s.period_ms for s in self.channels.values()) if self.channels else 0.0

    def is_empty(self) -> bool:
        return len(self.channels) == 0


class ControlCommand(str, Enum):
    """Discrete hardware commands sent through ``ControllerThread.request_write``.

    Using an enum instead of magic strings makes dispatch explicit and avoids
    accidental collisions with numeric values (e.g. ``DataActuator == 'home'``
    would raise a ``TypeError``).

    ``HOME``  — move to the home position.
    ``STOP``  — abort the current motion immediately.
    """
    HOME = 'home'
    STOP = 'stop'


# ---------------------------------------------------------------------------
# Plugin parent shim
# ---------------------------------------------------------------------------

class _StatusSig:
    """Minimal status_sig duck-type so old plugins can call parent.status_sig.emit()."""

    def __init__(self, ct: 'ControllerThread') -> None:
        self._ct = ct

    def emit(self, cmd: ThreadCommand) -> None:
        """Forward a ThreadCommand from the plugin to ControllerThread signals.

        Plugin settings changes (``update_settings`` / ``units`` commands) are
        relayed via ``settings_changed`` so the GUI thread can sync them back to
        the shared hw_settings Parameter.  All other text is forwarded as
        ``status_message``.
        """
        attr = cmd.attribute
        command = cmd.command          # may be str or StrEnum (compares equal to str)

        # --- in-motion position updates ----------------------------------------
        if command in ('check_position', 'get_actuator_value') and attr is not None:
            channel = getattr(self._ct._plugin, 'axis_name', '')
            self._ct.data_ready.emit(channel, attr, False)
            return

        # --- settings changes --------------------------------------------------
        if command == 'update_settings':
            # attr == [path, data, change]
            if isinstance(attr, (list, tuple)) and len(attr) >= 2:
                path, data = attr[0], attr[1]
                change = attr[2] if len(attr) > 2 else 'value'
                if path is not None:
                    channel = getattr(self._ct._plugin, 'axis_name', '')
                    self._ct.settings_changed.emit(channel, path, data, change)
                    return
        if command == 'units' and isinstance(attr, str):
            # axis_unit.setter fires synchronously inside axis_name.setter after
            # the settings value is already updated, so axis_name already reflects
            # the new channel at this point.
            channel = getattr(self._ct._plugin, 'axis_name', '')
            self._ct.settings_changed.emit(channel, ['units'], attr, 'value')
            return

        # --- plain text status -------------------------------------------------
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
    data_ready          = Signal(str, object, bool)  # (channel, DataToExport, is_temp)
    change_done         = Signal(str, object)        # (channel, DataActuator)
    hardware_status     = Signal(bool, str)          # (connected, info)
    status_message      = Signal(str)                # text for DAQ status bars
    settings_changed    = Signal(str, list, object, str)  # (channel, path, data, change)
    capabilities_signal = Signal(object)             # Capabilities

    def __init__(self, plugin_class: type, settings: 'Parameter') -> None:
        super().__init__()
        self._plugin_class = plugin_class
        self._settings_ref = settings           # shared hw_settings (GUI thread)
        self._plugin: Any = None
        self._controller: Any = None            # shared SDK object
        # ── Grab-timer state ─────────────────────────────────────────────────
        # Named groups: each _ReadGroup owns one QTimer + grab_in_flight guard.
        # group='' is the default shared group (original single-group behaviour).
        # group='detector', group='actuator', etc. for combined instruments.
        self._groups: dict[str, _ReadGroup] = {}
        # Solo channels: group=None; each gets its own independent QTimer.
        self._solo: dict[str, tuple[_ChannelState, QTimer]] = {}
        # _grab_in_flight serialises grab_data() calls across ALL modes (group
        # timers, solo timers, snaps).  Only one grab_data() can be outstanding
        # at a time per plugin instance.
        self._grab_in_flight: bool = False
        # _pending_group records which named group triggered the current grab
        # so _on_detector_data_ready can fan out to the right channels.
        # None means solo or snap; _pending_channel holds the channel in that case.
        self._pending_group: str | None = None
        self._pending_channel: str = ''         # channel of in-flight move/grab

    # ── Slots ← GUI thread ───────────────────────────────────────────────────

    @Slot()
    def ini_hardware(self) -> None:
        """Instantiate the plugin, open hardware, emit capabilities + status.

        Dispatches to the correct init path based on the plugin type:
        - new-style (``open`` API): _ini_new_style
        - old-style actuator (``ini_stage``): _ini_old_style_actuator
        - old-style detector (``ini_detector``): _ini_old_style_detector
        """
        try:
            if self._is_new_style():
                self._ini_new_style()
            elif self._is_combined():
                self._ini_combined()
            elif self._is_old_style_actuator():
                self._ini_old_style_actuator()
            else:
                self._ini_old_style_detector()
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot()
    def close_hardware(self) -> None:
        """Stop all grab timers, close the plugin, reset state."""
        for group in self._groups.values():
            if group.timer is not None:
                group.timer.stop()
        self._groups.clear()
        for _, (_, timer) in list(self._solo.items()):
            timer.stop()
        self._solo.clear()
        self._grab_in_flight = False
        self._pending_group = None

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

        For old-style actuators: calls ``get_actuator_value``.
        For old-style detectors: calls ``grab_data``; result arrives via dte_signal.
        For new-style plugins: calls ``query_data``.
        """
        if self._plugin is None:
            return
        try:
            if self._is_new_style():
                dte = self._plugin.query_data(names=[channel], fresh=fresh)
                self.data_ready.emit(channel, dte, False)
            elif self._is_old_style_actuator():
                self._read_old_style_actuator(channel)
            else:
                self._read_old_style_detector(channel)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, int)
    def request_snap(self, channel: str, Naverage: int) -> None:
        """One-shot snap; passes *Naverage* to the plugin when it supports hardware averaging.

        Always emits exactly one ``data_ready`` regardless of *Naverage* —
        software averaging across multiple grabs is the subscriber's responsibility.
        """
        if self._plugin is None:
            return
        try:
            if self._is_new_style():
                dte = self._plugin.query_data(names=[channel], fresh=True)
                self.data_ready.emit(channel, dte, False)
            elif self._is_old_style_detector():
                # request_snap is always a detector operation (DAQ_Viewer).
                # Check detector before actuator so combined plugins route here.
                self._snap_old_style_detector(channel, Naverage)
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
    @Slot(str, float, str)
    def start_grab(self, channel: str, period_ms: float, group: str | None = '') -> None:
        """Register a subscriber for periodic reads on *channel*.

        Parameters
        ----------
        channel :
            Channel name to poll ('' = broadcast / single-axis plugin).
        period_ms :
            Desired polling period in milliseconds.  The *effective* period
            is the minimum across all active subscribers on this channel
            (fastest-wins policy).
        group : str or None, default ''
            Named read group this channel belongs to.

            ``''`` (default) — the implicit shared group; one hardware read
            per tick fans out to all channels in this group.  Suitable for
            multi-axis controllers that return all positions in one SDK call.

            Any other string — a separate group with its own QTimer and its
            own grab-in-flight guard.  Use distinct group names when parts of
            a combined instrument need independent polling rates or when
            actuator polling must not be blocked by a slow detector grab
            (e.g. ``group='detector'`` vs ``group='actuator'``).

            ``None`` — solo: the channel gets its own independent QTimer,
            completely decoupled from every other channel.
        """
        if group is not None:
            if group not in self._groups:
                self._groups[group] = _ReadGroup(channels={})
            rg = self._groups[group]
            state = rg.channels.setdefault(channel, _ChannelState())
            state.subscribe(period_ms)
            self._update_group(group)
        else:
            if channel in self._solo:
                state, timer = self._solo[channel]
                state.subscribe(period_ms)
                timer.setInterval(int(state.period_ms))
            else:
                state = _ChannelState()
                state.subscribe(period_ms)
                timer = QTimer(self)
                timer.setInterval(int(period_ms))
                timer.timeout.connect(lambda: self._solo_tick(channel))
                timer.start()
                self._solo[channel] = (state, timer)

    @Slot(str)
    def stop_grab(self, channel: str) -> None:
        """Unregister one subscriber for *channel*.

        Searches named groups first, then solo.  The timer is stopped only
        when the last subscriber for the last channel in a group leaves.
        """
        for group_name, rg in list(self._groups.items()):
            if channel in rg.channels:
                last = rg.channels[channel].unsubscribe()
                if last:
                    del rg.channels[channel]
                self._update_group(group_name)
                break
        else:
            if channel in self._solo:
                state, timer = self._solo[channel]
                if state.unsubscribe():
                    timer.stop()
                    del self._solo[channel]
            else:
                return

        # Stop hardware acquisition when all channels everywhere are gone.
        if not self._groups and not self._solo:
            if self._plugin is not None and self._is_old_style_detector():
                try:
                    self._plugin.stop()
                except Exception:
                    pass

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

    # ── Internal: grab-timer machinery ───────────────────────────────────────

    def _update_group(self, group_name: str) -> None:
        """Create, retune, or tear down the QTimer for *group_name*."""
        rg = self._groups.get(group_name)
        if rg is None or rg.is_empty():
            if rg is not None and rg.timer is not None:
                rg.timer.stop()
            self._groups.pop(group_name, None)
            return
        period = int(rg.period_ms)
        if rg.timer is None:
            timer = QTimer(self)
            # Capture group_name by value via default argument.
            timer.timeout.connect(lambda gn=group_name: self._on_group_tick(gn))
            rg.timer = timer
        rg.timer.setInterval(period)
        if not rg.timer.isActive():
            rg.timer.start()

    def _on_group_tick(self, group_name: str) -> None:
        """One hardware read for all channels in *group_name*; fan out data_ready.

        For new-style plugins: one query_data(names=all_channels) call.
        For old-style detectors: one grab_data() call; the grab_in_flight guard
            on the group prevents re-entry; _on_detector_data_ready fans out the
            single DTE to every channel in the group.
        For old-style actuators: one get_actuator_value() per channel
            (sequential reads within a single event-loop tick).
        """
        rg = self._groups.get(group_name)
        if rg is None or rg.is_empty() or self._plugin is None:
            return
        channels = list(rg.channels.keys())
        try:
            if self._is_new_style():
                dte = self._plugin.query_data(names=channels, fresh=True)
                for ch in channels:
                    self.data_ready.emit(ch, dte, False)
            elif self._is_old_style_detector():
                if self._grab_in_flight:
                    return
                self._grab_in_flight = True
                self._pending_group = group_name
                self._plugin.grab_data(Naverage=1)
            elif self._is_old_style_actuator():
                for ch in channels:
                    self._read_old_style_actuator(ch)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    def _solo_tick(self, channel: str) -> None:
        """Periodic read for one independently-timed (solo) channel."""
        if self._plugin is None or channel not in self._solo:
            return
        try:
            if self._is_new_style():
                dte = self._plugin.query_data(names=[channel], fresh=True)
                self.data_ready.emit(channel, dte, False)
            elif self._is_old_style_detector():
                if self._grab_in_flight:
                    return
                self._grab_in_flight = True
                self._pending_group = None
                self._pending_channel = channel
                self._plugin.grab_data(Naverage=1)
            elif self._is_old_style_actuator():
                self._read_old_style_actuator(channel)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    # ── Internal: plugin-type detection ──────────────────────────────────────

    def _is_old_style_actuator(self) -> bool:
        """True for plugins that have ``ini_stage`` (pure actuator or combined)."""
        obj = self._plugin if self._plugin is not None else self._plugin_class
        return hasattr(obj, 'ini_stage')

    def _is_old_style_detector(self) -> bool:
        """True for plugins that have ``ini_detector`` (pure detector or combined)."""
        obj = self._plugin if self._plugin is not None else self._plugin_class
        return hasattr(obj, 'ini_detector')

    def _is_combined(self) -> bool:
        """True for plugins that expose both actuator and detector interfaces.

        Combined plugins represent instruments with multiple roles on one SDK
        (e.g. a camera stage that moves X/Y and also acquires images).
        ``ini_stage`` is called first; it creates the SDK.  ``ini_detector``
        is called next and receives the same controller object.
        """
        return self._is_old_style_actuator() and self._is_old_style_detector()

    def _is_new_style(self) -> bool:
        """True for plugins that use the new open/query_data/change_to API."""
        return not (self._is_old_style_actuator() or self._is_old_style_detector())

    # ── Internal: new-style plugin ────────────────────────────────────────────

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

    def _ini_combined(self) -> None:
        """Initialise a plugin that has both actuator and detector interfaces.

        ``ini_stage`` runs first and creates (or receives) the SDK instance.
        ``ini_detector`` is called next with the same controller so both roles
        share one underlying hardware object.
        """
        shim = _PluginParentShim(self, self._plugin_class.__name__)
        plugin = self._plugin_class(
            parent=shim,
            params_state=self._settings_ref.saveState(),
        )
        info, initialized = plugin.ini_stage(self._controller)
        if not initialized:
            self.hardware_status.emit(False, str(info))
            return
        self._controller = plugin.controller
        plugin.move_done_signal.connect(self._on_move_done)

        det_info, det_initialized = plugin.ini_detector(self._controller)
        if not det_initialized:
            self.hardware_status.emit(False, str(det_info))
            return
        self._plugin = plugin
        plugin.dte_signal.connect(self._on_detector_data_ready)
        if hasattr(plugin, 'dte_signal_temp'):
            plugin.dte_signal_temp.connect(self._on_detector_temp_data_ready)
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
        self.data_ready.emit(channel, pos, False)

    def _write_old_style_actuator(self, channel: str, value: object) -> None:
        """Dispatch a hardware command to an old-style actuator plugin.

        *value* is either a ``DataActuator`` (absolute target) or a
        ``ControlCommand`` enum member (``HOME`` / ``STOP``).

        ``STOP`` halts the poll timer first, then calls ``plugin.stop_motion()``.
        Most plugins implement ``stop_motion`` by calling ``self.move_done()``,
        which emits ``move_done_signal`` — so ``_on_move_done`` / ``change_done``
        fire normally, reporting the position where the axis stopped.

        ``HOME`` and ``move_abs`` both start the poll timer after initiating
        motion (non-blocking QTimer).
        """
        if channel and hasattr(self._plugin, 'axis_name'):
            if self._plugin.axis_name != channel:
                self._plugin.axis_name = channel

        if value is ControlCommand.STOP:
            # Stop polling first so the timer does not fire during/after the abort.
            self._plugin.poll_timer.stop()
            self._plugin.stop_motion()   # plugin calls move_done() → move_done_signal
            return

        self._pending_channel = channel
        self._plugin.move_is_done = False
        if value is ControlCommand.HOME:
            self._plugin.move_home()
        else:
            self._plugin.move_abs(self._to_plugin_units(value))
        self._plugin.poll_moving()   # starts QTimer, returns immediately

    def _to_plugin_units(self, value: object) -> object:
        """Convert a DataActuator to the form expected by an old-style plugin.

        Old-style float plugins (``data_actuator_type == DataActuatorType.float``)
        expect a plain Python float in ``plugin.axis_unit``.  DataActuator plugins
        expect a DataActuator whose ``.units`` is already set to ``plugin.axis_unit``.

        This mirrors the conversion that ``ActuatorWorker.move_abs`` performed so
        the plugin always receives its native unit, regardless of what display unit
        the GUI is using (e.g. meters displayed in the spinbox vs. µm in the plugin).

        If the plugin does not declare ``data_actuator_type`` (non-standard or mock
        plugins), *value* is passed through unchanged.
        """
        data_actuator_type = getattr(self._plugin, 'data_actuator_type', None)
        if data_actuator_type is None:
            return value
        from pymodaq.control_modules.move_utility_classes import (
            check_units, DataActuatorType,
        )
        axis_unit = self._plugin.axis_unit
        value = check_units(value, axis_unit)
        if data_actuator_type == DataActuatorType.float:
            return value.units_as(axis_unit).value()
        else:
            value.units = axis_unit
            return value

    @Slot(object)  # DataActuator
    def _on_move_done(self, data_actuator: object) -> None:
        """Receive move completion from the plugin; emit change_done."""
        channel = self._pending_channel
        self._pending_channel = ''
        self.change_done.emit(channel, data_actuator)

    # ── Internal: old-style detector ─────────────────────────────────────────

    def _ini_old_style_detector(self) -> None:
        """Initialise an old-style DAQ_Viewer_base plugin."""
        shim = _PluginParentShim(self, self._plugin_class.__name__)
        plugin = self._plugin_class(
            parent=shim,
            params_state=self._settings_ref.saveState(),
        )
        info, initialized = plugin.ini_detector(self._controller)
        if not initialized:
            self.hardware_status.emit(False, str(info))
            return
        self._controller = plugin.controller
        self._plugin = plugin
        plugin.dte_signal.connect(self._on_detector_data_ready)
        if hasattr(plugin, 'dte_signal_temp'):
            plugin.dte_signal_temp.connect(self._on_detector_temp_data_ready)
        self.hardware_status.emit(True, str(info))

    def _read_old_style_detector(self, channel: str) -> None:
        """Single grab (Naverage=1); used by request_read for one-shot reads."""
        self._snap_old_style_detector(channel, Naverage=1)

    def _snap_old_style_detector(self, channel: str, Naverage: int = 1) -> None:
        """Trigger one grab (snap / one-shot path).

        Passes *Naverage* to the plugin only when hardware averaging is
        supported; software averaging is the subscriber's responsibility.
        """
        if self._grab_in_flight:
            return
        self._grab_in_flight = True
        self._pending_group = None
        self._pending_channel = channel
        hw_avg = getattr(self._plugin, 'hardware_averaging', False)
        self._plugin.grab_data(Naverage=Naverage if hw_avg else 1)

    @Slot(object)  # DataToExport
    def _on_detector_data_ready(self, dte: object) -> None:
        """Receive grab completion from the plugin; emit data_ready.

        _pending_group is set when the grab was triggered by a named group's
        timer.  In that case the single DTE is fanned out to every channel in
        the group.  Otherwise _pending_channel holds the solo/snap channel name.
        """
        self._grab_in_flight = False
        group_name = self._pending_group
        self._pending_group = None
        if group_name is not None:
            rg = self._groups.get(group_name)
            if rg is not None:
                for ch in list(rg.channels.keys()):
                    self.data_ready.emit(ch, dte, False)
        else:
            channel = self._pending_channel
            self._pending_channel = ''
            self.data_ready.emit(channel, dte, False)

    @Slot(object)  # DataToExport
    def _on_detector_temp_data_ready(self, dte: object) -> None:
        """Receive mid-grab temporary data; emit data_ready(is_temp=True)."""
        group_name = self._pending_group
        if group_name is not None:
            rg = self._groups.get(group_name)
            if rg is not None:
                for ch in list(rg.channels.keys()):
                    self.data_ready.emit(ch, dte, True)
        else:
            self.data_ready.emit(self._pending_channel, dte, True)

    # ── Internal: new-style push mode ────────────────────────────────────────

    def _on_plugin_new_data(self, dte: object) -> None:
        """Fan out a push-mode DataToExport to per-channel data_ready signals."""
        for dwa in getattr(dte, 'data', []):
            channel = getattr(dwa, 'name', None)
            if channel is not None:
                self.data_ready.emit(channel, dte, False)
