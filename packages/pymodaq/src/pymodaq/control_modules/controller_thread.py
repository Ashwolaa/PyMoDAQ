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

Plugin-style dispatch
---------------------
Every public slot and timer callback dispatches to a style-specific helper.
The mapping is:

New-style (``open`` / ``query_data`` / ``change_to`` API):
    init        → ``_ini_new_style``
    periodic    → ``_on_group_tick`` / ``_solo_tick``  (``new_style`` branch)
    one-shot    → ``request_read`` / ``request_snap``  (new-style branch)
    write       → ``request_write``                    (new-style branch)
    push-mode   → ``_on_plugin_new_data``

Old-style actuator (``ini_stage`` / ``move_abs`` / ``get_actuator_value``):
    init        → ``_ini_old_style_actuator``
    periodic    → ``_on_group_tick`` / ``_solo_tick``  (``actuator`` branch)
    one-shot    → ``_read_old_style_actuator``
    write       → ``_write_old_style_actuator``
    move done   → ``_on_move_done``
    axis mux    → ``_emit_channel_state``, ``_axis_switching``  ← old-style only

Old-style detector (``ini_detector`` / ``grab_data``):
    init        → ``_ini_old_style_detector``
    periodic    → ``_on_group_tick`` / ``_solo_tick``  (``detector`` branch)
    snap        → ``_snap_old_style_detector``
    grab done   → ``_on_detector_data_ready`` / ``_on_detector_temp_data_ready``

Old-style combined (both ``ini_stage`` + ``ini_detector``):
    init        → ``_ini_combined``
    per-role    → same old-style actuator / detector paths above

Detection helpers (used throughout):
    ``_is_new_style``        → True for open/query_data/change_to API
    ``_is_old_style_actuator`` → True if plugin has ``ini_stage``
    ``_is_old_style_detector`` → True if plugin has ``ini_detector``
    ``_is_combined``           → True if plugin has both
    ``_resolve_role``          → maps 'auto'/'actuator'/'detector' to dispatch key

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

from qtpy.QtCore import QObject, Signal, Slot, QTimer, QSignalBlocker

from pymodaq_utils.utils import ThreadCommand

if TYPE_CHECKING:
    from pymodaq_gui.parameter import Parameter
    from pymodaq.control_modules.move_utility_classes import DataActuatorType

_UNSET = object()  # sentinel for _params_state default

__all__ = ['ControllerThread', 'ControlCommand']

@dataclass
class _AveragingState:
    """Per-channel software averaging state for old-style detectors.

    CT accumulates frames here and only emits ``data_ready`` when *Naverage*
    frames have been collected.  Between frames ``_grab_in_flight`` stays True
    so the periodic timer cannot start a competing grab.

    ``show_intermediate`` mirrors ``DetectorWorker.show_averaging``: when True,
    each intermediate average is broadcast as a temp frame so the viewer can
    display live progress.
    """
    Naverage: int
    ind: int = 0
    datas: object = None           # DataToExport running average, or None
    show_intermediate: bool = False


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

    role : str
        Dispatch key for hardware reads: ``'auto'`` (resolve from plugin type),
        ``'actuator'`` (always call ``get_actuator_value``), or
        ``'detector'`` (always call ``grab_data``).  Explicit roles are
        required for combined plugins where a single plugin instance exposes
        both interfaces; ``'auto'`` is correct for single-role plugins.
    """
    channels: dict  # str → _ChannelState; plain dict avoids dataclass field issues
    timer: Any = None           # QTimer | None
    role: str = 'auto'          # 'auto' | 'actuator' | 'detector'

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
        if self._ct._axis_switching:
            return  # suppress all side-effects while switching axis for a read/write
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

        # --- forward unhandled commands to subscribers (e.g. update_main_settings,
        #     show_splash, close_splash, lcd) ------------------------------------
        self._ct.custom_command.emit(cmd)
        # Also propagate a human-readable text for the status bar.
        if isinstance(attr, str):
            self._ct.status_message.emit(attr)
        elif isinstance(attr, (list, tuple)) and attr and isinstance(attr[0], str):
            self._ct.status_message.emit(str(attr[0]))


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
    custom_command      = Signal(object)             # (ThreadCommand,) unhandled plugin commands

    def __init__(self, plugin_class: type, params_state: dict | None = None) -> None:
        super().__init__()
        self._plugin_class = plugin_class
        self._params_state: dict | None = params_state  # initial config dict (safe across threads)
        self._plugin: Any = None
        self._plugin_settings: Any = None              # plugin's working Parameter (hardware thread)
        self._controller: Any = None            # shared SDK object
        # ── Grab-timer state ─────────────────────────────────────────────────
        # Named groups: each _ReadGroup owns one QTimer + grab_in_flight guard.
        # group='' is the default shared group (original single-group behaviour).
        # group='detector', group='actuator', etc. for combined instruments.
        self._groups: dict[str, _ReadGroup] = {}
        # Solo channels: group=None; each gets its own independent QTimer.
        # Tuple layout: (ChannelState, QTimer, role_str)
        self._solo: dict[str, tuple[_ChannelState, Any, str]] = {}
        # _grab_in_flight serialises grab_data() calls across ALL modes (group
        # timers, solo timers, snaps).  Only one grab_data() can be outstanding
        # at a time per plugin instance.
        self._grab_in_flight: bool = False
        # _pending_group records which named group triggered the current grab
        # so _on_detector_data_ready can fan out to the right channels.
        # None means solo or snap; _pending_channel holds the channel in that case.
        self._pending_group: str | None = None
        self._pending_channel: str = ''         # channel of in-flight move/grab

        # Per-channel software averaging state (old-style detectors only).
        # Keyed by channel name; created/updated by set_averaging().
        # Cleared on close_hardware() or when averaging completes.
        self._averaging: dict[str, _AveragingState] = {}  # [old-style detector only]

        # ── Old-style-only state ─────────────────────────────────────────────
        # The fields below are needed because old-style plugins have a single
        # ``axis_name`` slot that the CT must time-multiplex across channels.
        # New-style plugins expose per-channel APIs (query_data / change_to)
        # so axis switching is never needed there.

        # Set to True while switching axis_name for a read/write so that
        # spurious settings_changed emissions (units, epsilon side effects
        # of axis_name.setter) are not forwarded to the GUI subscribers.
        self._axis_switching: bool = False    # [old-style only]

        # True while _on_group_tick is iterating over channels.  Used by
        # _emit_channel_state to suppress redundant unit emissions that occur
        # on EVERY tick when the group reads multiple axes in sequence: the
        # axis-switch to Y emits units(Y) on tick 1; suppressing it on tick
        # 2, 3, … prevents _sync_units_ui → spinbox.setOpts() from firing
        # every tick and stealing keyboard focus from input spinboxes.
        # Explicit request_read() calls are NOT suppressed — _in_group_tick
        # is False outside of _on_group_tick.
        self._in_group_tick: bool = False     # [old-style only]

        # Last units value emitted per channel via settings_changed.
        # Checked by _emit_channel_state when _in_group_tick is True to decide
        # whether to suppress a redundant emission.
        self._emitted_units: dict[str, str] = {}  # [old-style only]

    # ── Plugin settings helpers ──────────────────────────────────────────────

    def _plugin_params_state(self) -> dict | None:
        """Return params_state with the 'name' key removed.

        The module's params_state has ``name='actuator_settings'`` (or
        ``'detector_settings'``).  Passing it unchanged to a plugin's
        ``__init__`` causes ``Parameter.restoreState`` to rename the
        plugin's root parameter from ``'Settings'`` to
        ``'actuator_settings'``.  Any subsequent ``settings.child('units')``
        call (flat path used by old-style plugins) then raises::

            ParameterError: Parameter actuator_settings has no child named units

        Stripping ``'name'`` prevents the rename; the plugin's root stays
        ``'Settings'`` and per-channel lookup paths resolve correctly.
        """
        state = self._params_state
        if isinstance(state, dict) and 'name' in state:
            return {k: v for k, v in state.items() if k != 'name'}
        return state

    def _create_plugin_settings(self) -> 'Parameter':
        """Create a fresh Parameter in the hardware thread for new-style plugins.

        Old-style plugins create their own ``self.settings`` in ``__init__``;
        this method is only needed for new-style plugins that receive a
        settings object via ``plugin.open(settings)``.
        """
        from pymodaq_gui.parameter import Parameter
        all_params = getattr(self._plugin_class, 'params', [])
        s = Parameter.create(name='Settings', type='group', children=all_params)
        if self._params_state is not None:
            s.restoreState(self._params_state, addChildren=False, removeChildren=False)
        s.sigTreeStateChanged.connect(self._on_plugin_settings_changed)
        return s

    # Paths that should never be echoed back via settings_changed because they
    # are module-controlled (each DAQ_Move picks its own axis independently).
    _AXIS_PATHS: frozenset = frozenset({
        ('controller', 'axis'),
        ('axis_settings', 'axis'),
    })

    def _on_plugin_settings_changed(self, param: object, changes: list) -> None:
        """Relay plugin settings changes to the GUI thread via settings_changed.

        Runs in the hardware thread (direct connection from hardware-thread
        Parameter).  Qt's queued delivery carries settings_changed to GUI.

        Axis-selector paths are excluded: they are set by each DAQ_Move
        independently and must not be echoed back, which would otherwise
        overwrite another module's axis choice whenever the CT switches axes.
        """
        if self._plugin_settings is None or self._axis_switching:
            return
        for p, change, data in changes:
            path = self._plugin_settings.childPath(p)
            if path and change == 'value':
                if tuple(path) in self._AXIS_PATHS:
                    continue
                channel = getattr(self._plugin, 'axis_name', '') if self._plugin else ''
                self.settings_changed.emit(channel, list(path), data, change)

    def _connect_plugin_settings(self, plugin: object) -> None:
        """Wire an old-style plugin's own settings tree into the CT relay.

        Called after plugin construction but before ``ini_stage`` /
        ``ini_detector`` so that any settings writes during hardware init
        are captured and forwarded to the GUI thread.
        """
        s = getattr(plugin, 'settings', None)
        if s is not None:
            s.sigTreeStateChanged.connect(self._on_plugin_settings_changed)
            self._plugin_settings = s

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
        for _, (_, timer, _) in list(self._solo.items()):
            timer.stop()
        self._solo.clear()
        self._grab_in_flight = False
        self._pending_group = None
        self._averaging.clear()

        if self._plugin_settings is not None:
            try:
                self._plugin_settings.sigTreeStateChanged.disconnect(
                    self._on_plugin_settings_changed
                )
            except Exception:
                pass
            self._plugin_settings = None

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
            if self._is_new_style():                     # [new-style]
                dte = self._plugin.query_data(names=[channel], fresh=fresh)
                self.data_ready.emit(channel, dte, False)
            elif self._is_old_style_actuator():          # [old-style actuator]
                self._read_old_style_actuator(channel)
            else:                                        # [old-style detector]
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
            if self._is_new_style():                     # [new-style]
                dte = self._plugin.query_data(names=[channel], fresh=True)
                self.data_ready.emit(channel, dte, False)
            elif self._is_old_style_detector():          # [old-style detector / combined]
                # Check detector before actuator so combined plugins route here.
                self._snap_old_style_detector(channel, Naverage)
            else:                                        # [old-style actuator]
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
            if self._is_new_style():      # [new-style]
                self._plugin.change_to(channel, value)
                self.change_done.emit(channel, value)
            else:                         # [old-style actuator]
                self._write_old_style_actuator(channel, value)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, float)
    @Slot(str, float, str)
    def start_grab(self, channel: str, period_ms: float, group: str | None = '',
                   role: str = 'auto') -> None:
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

            Any other string — a separate group with its own QTimer.  Use
            distinct group names when parts of a combined instrument need
            independent polling rates (e.g. ``group='detector'`` vs
            ``group='actuator'``).

            ``None`` — solo: the channel gets its own independent QTimer,
            completely decoupled from every other channel.
        role : str, default 'auto'
            How to read this channel when the timer fires.  Only relevant for
            combined plugins (those with both actuator and detector
            interfaces).

            ``'auto'``     — resolve from plugin type at tick time (correct
                             for single-role plugins; defaults to
                             ``'detector'`` for combined plugins).
            ``'actuator'`` — always call ``get_actuator_value``.
            ``'detector'`` — always call ``grab_data``.

            The role is fixed when the group is first created; later
            ``start_grab`` calls that join an existing group do not change
            its role.
        """
        if group is not None:
            if group not in self._groups:
                self._groups[group] = _ReadGroup(channels={}, role=role)
            rg = self._groups[group]
            state = rg.channels.setdefault(channel, _ChannelState())
            state.subscribe(period_ms)
            self._update_group(group)
        else:
            if channel in self._solo:
                state, timer, _role = self._solo[channel]
                state.subscribe(period_ms)
                timer.setInterval(int(state.period_ms))
            else:
                state = _ChannelState()
                state.subscribe(period_ms)
                timer = QTimer(self)
                timer.setInterval(int(period_ms))
                timer.timeout.connect(lambda: self._solo_tick(channel))
                timer.start()
                self._solo[channel] = (state, timer, role)

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
                state, timer, _role = self._solo[channel]
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

    # ── Slots ← GUI thread (detector-specific) ───────────────────────────────

    @Slot()
    def request_stop(self) -> None:
        """[old-style detector] Stop any ongoing grab immediately.

        Calls ``plugin.stop()``, stops all timer groups, and resets all
        in-flight grab state so the next snap or start_grab begins clean.
        """
        if self._plugin is not None and self._is_old_style_detector():
            try:
                self._plugin.stop()
            except Exception:
                pass
        for group in self._groups.values():
            if group.timer is not None:
                group.timer.stop()
        self._groups.clear()
        for _, (_, timer, _) in list(self._solo.items()):
            timer.stop()
        self._solo.clear()
        self._grab_in_flight = False
        self._pending_group = None
        self._pending_channel = ''
        self._averaging.clear()

    @Slot(str, int, bool)
    def set_averaging(self, channel: str, Naverage: int, show_intermediate: bool = False) -> None:
        """[old-style detector only] Configure software averaging for *channel*.

        Call this before ``request_snap`` / ``start_grab`` whenever Naverage > 1
        and the plugin does not support hardware averaging.  When Naverage <= 1
        any existing averaging state for the channel is cleared (pass-through mode).

        ``show_intermediate`` mirrors ``DetectorWorker.show_averaging``: if True,
        each partial average is broadcast as a temp frame so the viewer shows
        live progress.
        """
        if Naverage <= 1:
            self._averaging.pop(channel, None)
        else:
            existing = self._averaging.get(channel)
            if existing is not None:
                existing.Naverage = Naverage
                existing.show_intermediate = show_intermediate
            else:
                self._averaging[channel] = _AveragingState(
                    Naverage=Naverage, show_intermediate=show_intermediate
                )

    @Slot(str, object, int)
    def request_roi_select(self, channel: str, roi_info: object, ind_viewer: int) -> None:
        """[old-style detector only] Forward a ROI selection from a viewer widget to the plugin.

        Calls ``plugin.ROISelect(roi_info)`` if the plugin defines it.
        ``ind_viewer`` is forwarded to ``ROISelect`` when the plugin's signature
        accepts it; otherwise it is silently ignored.
        """
        if self._plugin is None:
            return
        roi_select = getattr(self._plugin, 'ROISelect', None)
        if roi_select is None:
            return
        try:
            import inspect
            sig = inspect.signature(roi_select)
            if len(sig.parameters) >= 2:
                roi_select(roi_info, ind_viewer)
            else:
                roi_select(roi_info)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    @Slot(str, object, int)
    def request_crosshair(self, channel: str, crosshair_info: object, ind_viewer: int) -> None:
        """[old-style detector only] Forward a crosshair-drag event to the plugin.

        Calls ``plugin.crosshairChanged(crosshair_info)`` if defined.
        """
        if self._plugin is None:
            return
        crosshair_changed = getattr(self._plugin, 'crosshairChanged', None)
        if crosshair_changed is None:
            return
        try:
            crosshair_changed(crosshair_info)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    # Per-channel param names in axis_settings (flat layout for old-style plugins)
    _FLAT_PER_CHANNEL_NAMES: frozenset = frozenset({'units', 'epsilon', 'timeout', 'bounds', 'scaling'})

    def _translate_module_path_to_plugin(self, path: list) -> list:
        """Translate a module-side settings path to the plugin's settings path.

        The module groups per-channel params under ``axis_settings``.
        For multi-axis new-style modules: ``['axis_settings', axis_name, 'units']``.
        For single-axis new-style modules: ``['axis_settings', 'units']``.
        Old-style plugins keep a flat layout (``axis`` lives at
        ``['controller', 'axis']``; others are top-level).

        New-style plugins that already have an ``axis_settings`` group need
        either no translation (if they also have per-axis sub-groups) or
        stripping of the per-axis level (if they have flat axis_settings).
        """
        if not path or path[0] != 'axis_settings' or self._plugin_settings is None:
            return list(path)

        # Check if plugin has axis_settings
        try:
            plugin_as = self._plugin_settings.child('axis_settings')
        except Exception:
            # Old-style plugin: no axis_settings group
            rest = list(path[1:])
            if rest and rest[0] == 'axis':
                return ['controller', 'axis'] + rest[1:]
            # path is ['axis_settings', axis_name?, 'units']: strip axis_settings + optional axis_name
            if len(rest) >= 2 and rest[0] not in self._FLAT_PER_CHANNEL_NAMES and rest[0] != 'axis':
                # rest[0] is axis_name, rest[1:] is the actual param path
                return list(rest[1:])
            return list(rest)

        # Plugin has axis_settings. Check if it has per-axis sub-groups.
        try:
            axis_param = plugin_as.child('axis')
            limits = axis_param.opts.get('limits', [])
            if isinstance(limits, list) and limits:
                first_name = str(limits[0])
            elif isinstance(limits, dict) and limits:
                first_name = str(list(limits.keys())[0])
            else:
                first_name = None

            if first_name is not None and first_name != '':
                try:
                    plugin_as.child(first_name)
                    # Plugin has per-axis sub-groups: path works as-is
                    return list(path)
                except Exception:
                    pass
        except Exception:
            pass

        # Plugin has flat axis_settings (single-axis or old-format multi-axis):
        # strip per-axis level from path if present.
        rest = list(path[1:])  # strip 'axis_settings'
        if (len(rest) >= 2
                and rest[0] not in self._FLAT_PER_CHANNEL_NAMES
                and rest[0] != 'axis'):
            # rest[0] is axis_name (e.g. 'X'), rest[1:] is the actual param path
            return ['axis_settings'] + rest[1:]
        return ['axis_settings'] + rest

    @Slot(list, object, str)
    def update_settings(self, path: list, data: object, change: str) -> None:
        """Relay a GUI hw_settings edit to the plugin's commit_settings(param).

        Translates the module-side path to the plugin's own layout before
        looking up the Parameter node, then applies the change under a
        QSignalBlocker (no re-trigger) and calls commit_settings.
        """
        if self._plugin is None or self._plugin_settings is None:
            return
        plugin_path = self._translate_module_path_to_plugin(path)
        with QSignalBlocker(self._plugin_settings):
            try:
                param = (self._plugin_settings.child(*plugin_path)
                         if plugin_path else self._plugin_settings)
                param.setValue(data)
            except Exception:
                return
        commit = getattr(self._plugin, 'commit_settings', None)
        if commit is None:
            return
        try:
            param = (self._plugin_settings.child(*plugin_path)
                     if plugin_path else self._plugin_settings)
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

        Dispatches based on the group's *role* (resolved via ``_resolve_role``):

        ``'new_style'``  — one ``query_data(names=all_channels)`` call; result
                           fanned out per channel.
        ``'detector'``   — one ``grab_data()`` call guarded by
                           ``_grab_in_flight``; ``_on_detector_data_ready``
                           fans the DTE to every channel in the group.
        ``'actuator'``   — one ``get_actuator_value()`` per channel
                           (sequential reads within a single event-loop tick);
                           never blocked by ``_grab_in_flight``.
        """
        rg = self._groups.get(group_name)
        if rg is None or rg.is_empty() or self._plugin is None:
            return
        channels = list(rg.channels.keys())
        role = self._resolve_role(rg.role)
        try:
            if role == 'new_style':      # [new-style]
                dte = self._plugin.query_data(names=channels, fresh=True)
                for ch in channels:
                    self.data_ready.emit(ch, dte, False)
            elif role == 'detector':     # [old-style detector / combined]
                if self._grab_in_flight:
                    return
                self._grab_in_flight = True
                self._pending_group = group_name
                self._plugin.grab_data(Naverage=1)
            else:                        # [old-style actuator]  role == 'actuator'
                self._in_group_tick = True
                try:
                    for ch in channels:
                        self._read_old_style_actuator(ch)
                finally:
                    self._in_group_tick = False
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    def _solo_tick(self, channel: str) -> None:
        """Periodic read for one independently-timed (solo) channel."""
        if self._plugin is None or channel not in self._solo:
            return
        _, _, stored_role = self._solo[channel]
        role = self._resolve_role(stored_role)
        try:
            if role == 'new_style':      # [new-style]
                dte = self._plugin.query_data(names=[channel], fresh=True)
                self.data_ready.emit(channel, dte, False)
            elif role == 'detector':     # [old-style detector / combined]
                if self._grab_in_flight:
                    return
                self._grab_in_flight = True
                self._pending_group = None
                self._pending_channel = channel
                self._plugin.grab_data(Naverage=1)
            else:                        # [old-style actuator]  role == 'actuator'
                self._read_old_style_actuator(channel)
        except Exception as exc:
            self.hardware_status.emit(False, str(exc))

    # ── Internal: role resolution ────────────────────────────────────────────

    def _resolve_role(self, role: str) -> str:
        """Map a *role* string to a concrete dispatch key used by tick handlers.

        Return values and their dispatch targets:

        ``'new_style'``  → ``_on_group_tick`` / ``_solo_tick`` new-style branch
                           (plugin.query_data)                    [new-style only]
        ``'detector'``   → ``_snap_old_style_detector``           [old-style detector / combined]
        ``'actuator'``   → ``_read_old_style_actuator``           [old-style actuator / combined]

        New-style plugins always resolve to ``'new_style'`` regardless of the
        requested role.  For old-style plugins, ``'auto'`` maps to
        ``'detector'`` when the plugin has ``ini_detector`` (including
        combined plugins), and to ``'actuator'`` otherwise.  Explicit
        ``'actuator'`` / ``'detector'`` values are passed through unchanged
        and let callers target one side of a combined plugin directly.
        """
        if self._is_new_style():                                  # [new-style]
            return 'new_style'
        if role == 'auto':                                        # [old-style]
            return 'detector' if self._is_old_style_detector() else 'actuator'
        return role   # explicit 'actuator' or 'detector'        # [old-style combined]

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
        self._plugin_settings = self._create_plugin_settings()
        plugin = self._plugin_class()
        plugin.open(self._plugin_settings)
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
            params_state=self._plugin_params_state(),
        )
        # Wire plugin's own settings tree before ini_stage so settings changes
        # emitted during hardware init are forwarded to the GUI thread.
        self._connect_plugin_settings(plugin)
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
            params_state=self._plugin_params_state(),
        )
        self._connect_plugin_settings(plugin)
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

    def _emit_channel_state(self, channel: str) -> None:
        """[old-style actuator only] Re-emit per-channel state (units) after a suppressed axis switch.

        Old-style plugins expose one ``axis_name`` slot; the CT must switch it
        before each per-channel read.  ``_axis_switching`` suppresses all
        ``settings_changed`` emissions during the switch, so after the switch
        completes we must re-emit state that genuinely changed.

        Suppression strategy — two layers:

        1. **Always**: skip emission when ``unit`` is None (plugin does not
           expose ``axis_unit``).
        2. **Inside group ticks only** (``_in_group_tick=True``): skip
           emission when the unit for *channel* matches the last emitted value
           (``_emitted_units``).  Group ticks read all channels every period,
           so without this guard every tick causes _sync_units_ui →
           spinbox.setOpts() on all input spinboxes, triggering a PyQtGraph
           redraw that steals keyboard focus.
        3. **Outside group ticks** (explicit ``request_read``): always emit.
           A subscriber that newly attaches or a DAQ_Move that was waiting for
           its axis to be read deserves a fresh notification.
        """
        unit = getattr(self._plugin, 'axis_unit', None)
        if unit is None:
            return
        if self._in_group_tick and self._emitted_units.get(channel) == unit:
            return  # suppress redundant emission during periodic group tick
        self._emitted_units[channel] = unit
        self.settings_changed.emit(channel, ['units'], unit, 'value')

    def _read_old_style_actuator(self, channel: str) -> None:
        """One-shot position read for an old-style actuator plugin.

        Emits the raw return value of ``get_actuator_value``.  The receiver
        (``DAQ_Move._on_data_ready``) normalises it via ``_check_data_type``.

        After the read the plugin's axis is restored to ``_pending_channel``
        when a move is in progress on a different channel.  Without this,
        ``poll_timer.check_target_reached()`` would read the wrong axis on the
        next event-loop tick, causing spurious move-done or motion that never
        converges.
        """
        if channel and hasattr(self._plugin, 'axis_name'):
            if self._plugin.axis_name != channel:
                self._axis_switching = True
                try:
                    self._plugin.axis_name = channel
                finally:
                    self._axis_switching = False
                self._emit_channel_state(channel)
        pos = self._plugin.get_actuator_value()
        self.data_ready.emit(channel, pos, False)
        # Restore the plugin's axis to the channel under active motion so that
        # check_target_reached() always polls the correct axis.
        pending = self._pending_channel
        if (pending and pending != channel
                and hasattr(self._plugin, 'axis_name')
                and self._plugin.axis_name != pending):
            self._axis_switching = True
            try:
                self._plugin.axis_name = pending
            finally:
                self._axis_switching = False

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
                self._axis_switching = True
                try:
                    self._plugin.axis_name = channel
                finally:
                    self._axis_switching = False
                self._emit_channel_state(channel)
                # _current_value may carry units from the previous axis; refresh it
                # so check_target_reached can subtract current from target without a
                # pint DimensionalityError.
                try:
                    self._plugin.get_actuator_value()
                except Exception:
                    pass

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
            params_state=self._plugin_params_state(),
        )
        self._connect_plugin_settings(plugin)
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
        """[old-style detector] Receive grab completion from the plugin; emit data_ready.

        Resolves the affected channels from ``_pending_group`` (named group timer)
        or ``_pending_channel`` (solo / snap), then runs software averaging if
        ``set_averaging`` was called for those channels.

        Software averaging (non-blocking):
        - ``_grab_in_flight`` stays True between frames so the timer cannot
          fire a competing grab while accumulation is in progress.
        - When the target frame count is reached, the averaged DTE is published
          and the averaging counter resets for the next snap / grab cycle.
        - Intermediate frames are published as temp data when
          ``_AveragingState.show_intermediate`` is True.
        """
        group_name = self._pending_group
        self._pending_group = None

        # Resolve channel list from pending state.
        if group_name is not None:
            rg = self._groups.get(group_name)
            channels = list(rg.channels.keys()) if rg is not None else []
        else:
            channels = [self._pending_channel]
            self._pending_channel = ''

        for ch in channels:
            avg = self._averaging.get(ch)
            if avg is None or avg.Naverage <= 1:
                # No averaging: publish immediately.
                self._grab_in_flight = False
                self.data_ready.emit(ch, dte, False)
                continue

            # Software averaging: accumulate this frame.
            avg.ind += 1
            avg.datas = dte if avg.ind == 1 else dte.average(avg.datas, avg.ind)

            if avg.show_intermediate:
                self.data_ready.emit(ch, avg.datas, True)  # temp frame

            if avg.ind < avg.Naverage:
                # Chain next grab; _grab_in_flight stays True.
                self._pending_channel = ch
                self._plugin.grab_data(Naverage=1)
                return  # wait for next _on_detector_data_ready

            # All frames collected: publish final average and reset.
            self._grab_in_flight = False
            self.data_ready.emit(ch, avg.datas, False)
            avg.ind = 0
            avg.datas = None

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
