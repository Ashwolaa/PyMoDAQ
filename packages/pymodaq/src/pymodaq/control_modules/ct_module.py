"""Shared base for ControllerThread-backed control modules (DAQ_Move, DAQ_Viewer).

ControllerThreadModule provides the common lifecycle:
- attach to / detach from ControllerThread via ControllerRegistry
- relay hw_settings changes bidirectionally (GUI ↔ plugin thread)
- common slots: _on_hardware_status, _relay_hw_settings_change, _on_hw_settings_changed

Module-specific signals (write-request for actuators, start-grab for detectors)
and data-handling slots remain in the concrete subclasses.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from qtpy.QtCore import Signal, Slot, QSignalBlocker, QMetaObject, Qt

from pymodaq_utils.utils import ThreadCommand

from pymodaq.control_modules.utils import ParameterControlModule
from pymodaq.control_modules.controller_registry import ControllerRegistry, ControllerKey

if TYPE_CHECKING:
    from pymodaq.control_modules.controller_thread import ControllerThread
    from pymodaq_gui.parameter import Parameter

__all__ = ['ControllerThreadModule']


class ControllerThreadModule(ParameterControlModule):
    """Intermediate base class for ControllerThread-backed control modules.

    Provides attach/detach lifecycle, bidirectional hw_settings relay, and
    common slots.  Concrete subclasses add their own signals and data handlers.

    Subclasses must implement:
        _get_plugin_class()          → the plugin class for the selected instrument
        _connect_ct_signals(ct)      → connect module-specific CT signals
        _disconnect_ct_signals(ct)   → disconnect them

    Subclasses may override:
        _PER_CHANNEL_PARAMS          → frozenset of param names that are per-channel
        _derive_channel()            → return the channel name (default: '')
        _on_hardware_connected()     → called when hardware_status(True) fires
        _on_per_channel_param_changed(path, data) → e.g. update units suffix in UI
    """

    # Per-channel parameter identifiers: either a top-level name string (e.g.
    # 'units') or a full path tuple (e.g. ('controller', 'axis')).  Params that
    # match are kept in each module's LOCAL settings and are never mirrored to
    # the shared _hw_settings.
    _PER_CHANNEL_PARAMS: frozenset = frozenset()

    # Set to True in detector subclasses (DAQ_Viewer) to wire the detector-
    # specific cross-thread signals (_snap_request, _start_grab_request, etc.).
    # Actuator subclasses (DAQ_Move) leave this False so those signals are never
    # connected and produce no spurious disconnect warnings on detach.
    _uses_detector_signals: bool = False

    def _is_per_channel(self, path: list) -> bool:
        """Return True if *path* identifies a per-channel (per-module) parameter.

        Supports both top-level name strings and full path tuples so that
        nested params like ('controller', 'axis') can be flagged without
        making the entire 'controller' group per-channel.
        """
        if not path:
            return False
        return (path[0] in self._PER_CHANNEL_PARAMS
                or tuple(path) in self._PER_CHANNEL_PARAMS)

    # Signals that cross from the GUI thread into the hardware thread.
    _read_request      = Signal(str)               # (channel,) → ct.request_read
    _stop_grab_request = Signal(str)               # (channel,) → ct.stop_grab
    _settings_update   = Signal(list, object, str) # (path, data, change) → ct.update_settings

    # Detector-specific cross-thread signals  [old-style detector only]
    _start_grab_request = Signal(str, float)        # (channel, period_ms) → ct.start_grab
    _snap_request       = Signal(str, int)           # (channel, Naverage)  → ct.request_snap
    _stop_request       = Signal()                   # ()                   → ct.request_stop
    _set_averaging      = Signal(str, int, bool)     # (channel, N, show)   → ct.set_averaging
    _roi_select         = Signal(str, object, int)   # (channel, roi, idx)  → ct.request_roi_select
    _crosshair          = Signal(str, object, int)   # (channel, info, idx) → ct.request_crosshair

    def __init__(self, **kwargs):
        # Set CT attributes before ParameterControlModule (and its ParameterManager
        # parent) runs.  Parameter-tree change callbacks fire during that
        # construction and invoke _module_value_changed which reads self._ct.
        self._ct: Optional[ControllerThread] = None
        self._ct_key: Optional[ControllerKey] = None
        self._channel: str = ''
        self._hw_settings: Optional[Parameter] = None
        self._syncing_from_hw: bool = False
        self._init_failed: bool = False  # set True on hardware_status(False) for fast poll_init exit
        super().__init__(**kwargs)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _hw(self, *path):
        """Read a value from the shared hw_settings, falling back to local settings."""
        hw = getattr(self, '_hw_settings', None)
        if hw is not None:
            return hw[path]
        return self.settings[(self._hw_settings_name, *path)]

    def _hw_child(self, *path):
        """Return a Parameter node from hw_settings, falling back to local settings."""
        hw = getattr(self, '_hw_settings', None)
        if hw is not None:
            return hw.child(*path)
        return self.settings.child(self._hw_settings_name, *path)

    # ── Hooks (override in subclasses) ────────────────────────────────────────

    def _get_plugin_class(self) -> type:
        raise NotImplementedError

    def _derive_channel(self) -> str:
        """Return the channel name for this module ('' = broadcast/single-axis)."""
        return ''

    def _connect_ct_signals(self, ct: 'ControllerThread') -> None:
        """Connect module-specific CT signals after attach."""
        pass

    def _disconnect_ct_signals(self, ct: 'ControllerThread') -> None:
        """Disconnect module-specific CT signals before detach."""
        pass

    def _on_hardware_connected(self) -> None:
        """Called when hardware_status(True) fires; e.g. trigger initial read."""
        pass

    def _on_per_channel_param_changed(self, path: list, data) -> None:
        """Called after a per-channel param is written to local settings."""
        pass

    def _dispatch_command_hardware(self, command: ThreadCommand) -> None:
        """Handle a legacy ``command_hardware`` ThreadCommand.

        ``command_hardware`` predates the ControllerThread architecture and
        was historically wired to a per-module hardware-thread worker's
        ``queue_command``.  External callers (e.g. ``ModulesManager``, used
        by ``DAQ_Scan`` and other extensions) still emit commands on this
        signal to trigger grabs/moves.  Override in subclasses to translate
        those commands onto the CT-based public API (``grab_data``,
        ``move_abs``, ...).
        """
        pass

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init_hardware(self, do_init=True):
        """Attach to (or detach from) the shared ControllerThread."""
        if not do_init:
            self._detach_controller()
            return
        self._init_failed = False
        try:
            plugin_class = self._get_plugin_class()
            hw_cls = getattr(plugin_class, 'hardware_class', plugin_class)
            key = ControllerKey(
                hardware_class=hw_cls,
                controller_id=self.settings[self._hw_settings_name, 'controller', 'controller_ID'],
            )
            params_state = self.settings.child(self._hw_settings_name).saveState()
            ct, hw_settings = ControllerRegistry.get().attach(
                key, plugin_class, params_state=params_state, subscriber=self,
                exclude_params=self._PER_CHANNEL_PARAMS,
            )
            self._ct = ct
            self._ct_key = key
            # Derive channel from LOCAL settings before assigning _hw_settings.
            # axis_name uses _hw_child which falls back to local settings when
            # _hw_settings is None.  If we assign _hw_settings first, all
            # subscribers on the same CT read the same shared axis value and
            # end up with identical _channel (e.g. both 'X' instead of 'X' and
            # 'Theta').
            self._channel = self._derive_channel()
            self._hw_settings = hw_settings

            ct.hardware_status.connect(self._on_hardware_status)
            ct.status_message.connect(self.update_status)
            ct.settings_changed.connect(self._on_hw_settings_changed)
            ct.custom_command.connect(self.thread_status)

            self.command_hardware[ThreadCommand].connect(self._dispatch_command_hardware)

            self._read_request.connect(ct.request_read)
            self._stop_grab_request.connect(ct.stop_grab)
            self._settings_update.connect(ct.update_settings)

            # Detector signals: only connect when this module actually uses them.
            # DAQ_Move (actuator) must not get these wired — it never emits them
            # and the spurious connections produce disconnect warnings on detach.
            self._ct_detector_signals_connected = False
            if self._uses_detector_signals and hasattr(ct, 'request_snap'):
                self._start_grab_request.connect(ct.start_grab)
                self._snap_request.connect(ct.request_snap)
                self._stop_request.connect(ct.request_stop)
                self._set_averaging.connect(ct.set_averaging)
                self._roi_select.connect(ct.request_roi_select)
                self._crosshair.connect(ct.request_crosshair)
                self._ct_detector_signals_connected = True

            self._connect_ct_signals(ct)
            self.connect_leco(True)

            # Point the UI's settings action at the hw_settings panel for this
            # plugin class.  Move and Viewer on the same CT each get their own
            # panel (built from their respective plugin params).
            if self.ui is not None and hasattr(self.ui, 'use_shared_settings_action'):
                hw_panel = ControllerRegistry.get().get_hw_panel(key, plugin_class)
                hw_action = ControllerRegistry.get().get_hw_action(key, plugin_class)
                if hw_panel is not None and hw_action is not None:
                    self.ui.use_shared_settings_action(hw_action, hw_panel)

            # Second (and later) subscribers attach after the CT has already
            # emitted hardware_status(True).  They miss that signal, so
            # _on_hardware_connected (initial position read, units sync) is
            # never triggered.  Fire a synthetic status here.
            if getattr(ct, '_plugin', None) is not None:
                self._on_hardware_status(True, 'Hardware already initialized')
            else:
                # First subscriber: all signal connections are now in place.
                # Queue ini_hardware() in the hardware thread so that any
                # settings_changed emissions from ini_stage (e.g. units) arrive
                # AFTER settings_changed is connected above, not before.
                QMetaObject.invokeMethod(ct, 'ini_hardware',
                                         Qt.ConnectionType.QueuedConnection)
        except Exception as e:
            self.logger.exception(str(e))

    def _detach_controller(self):
        """Disconnect signals and release the registry reference."""
        self._pre_close_hardware()
        self.connect_leco(False)
        # Restore the per-module settings action before releasing the key.
        if self.ui is not None and hasattr(self.ui, 'release_shared_settings_action'):
            self.ui.release_shared_settings_action()
        if self._ct is not None:
            try:
                self._disconnect_ct_signals(self._ct)
                self._ct.hardware_status.disconnect(self._on_hardware_status)
                self._ct.status_message.disconnect(self.update_status)
                self._ct.settings_changed.disconnect(self._on_hw_settings_changed)
                self._ct.custom_command.disconnect(self.thread_status)
                self.command_hardware[ThreadCommand].disconnect(self._dispatch_command_hardware)
                self._read_request.disconnect(self._ct.request_read)
                self._stop_grab_request.disconnect(self._ct.stop_grab)
                self._settings_update.disconnect(self._ct.update_settings)
                if getattr(self, '_ct_detector_signals_connected', False):
                    self._start_grab_request.disconnect(self._ct.start_grab)
                    self._snap_request.disconnect(self._ct.request_snap)
                    self._stop_request.disconnect(self._ct.request_stop)
                    self._set_averaging.disconnect(self._ct.set_averaging)
                    self._roi_select.disconnect(self._ct.request_roi_select)
                    self._crosshair.disconnect(self._ct.request_crosshair)
                    self._ct_detector_signals_connected = False
            except Exception:
                pass
            self._ct = None
        if self._hw_settings is not None:
            self._hw_settings = None
        if self._ct_key is not None:
            ControllerRegistry.get().detach(self._ct_key, subscriber=self)
            self._ct_key = None
        self._initialized_state = False
        self.init_signal.emit(False)

    # ── Common CT slots ───────────────────────────────────────────────────────

    @Slot(bool, str)
    def _on_hardware_status(self, connected: bool, info: str):
        """Receive hardware connection status from ControllerThread."""
        self.update_status(f'Hardware initialized: {connected}  info: {info}')
        self._initialized_state = connected
        if not connected:
            self._init_failed = True  # lets poll_init exit immediately on failure
        if self.ui is not None:
            setattr(self.ui, self._ui_init_attr, connected)
        if connected:
            self._on_hardware_connected()
        self.init_signal.emit(connected)

    @Slot(object, object)
    def _relay_hw_settings_change(self, param, changes):
        """Forward hw_settings edits (from any subscriber) to the hardware thread."""
        if self._ct is None:
            return
        for p, change, data in changes:
            path = self._hw_settings.childPath(p)
            if path is not None:
                self._settings_update.emit(path, data, change)

    def _map_to_module_path(self, path: list) -> list:
        """Normalise a plugin-emitted param path to the module's local layout.

        Base implementation is an identity — subclasses override when their
        plugin may emit flat paths that need regrouping (e.g. DAQ_Move maps
        ``['units']`` → ``['axis_settings', 'units']``).
        """
        return list(path)

    @Slot(str, list, object, str)
    def _on_hw_settings_changed(self, channel: str, path: list, data, change: str):
        """Receive plugin-initiated settings changes and apply them selectively.

        Per-channel parameters (in _PER_CHANNEL_PARAMS) are written to this
        module's local settings under the ``axis_settings`` group, filtered
        by channel.  Old-style plugins emit flat paths (e.g. ``['units']``);
        ``_map_to_module_path`` normalises these to the grouped layout before
        writing.  Per-controller params are written to the shared _hw_settings.
        """
        if change != 'value' or not path:
            return

        mapped = self._map_to_module_path(path)

        if self._is_per_channel(mapped):
            if channel and channel != self._channel:
                return
            self._syncing_from_hw = True
            try:
                self.settings.child(self._hw_settings_name, *mapped).setValue(data)
            except Exception:
                pass
            finally:
                self._syncing_from_hw = False
            self._on_per_channel_param_changed(mapped, data)
            return

        if self._hw_settings is None:
            return
        with QSignalBlocker(self._hw_settings):
            try:
                self._hw_settings.child(*path).setValue(data)
            except Exception:
                pass
        # Mirror into local display so the module's own settings widget stays
        # in sync when another subscriber (or the plugin itself) changed a value.
        self._syncing_from_hw = True
        try:
            self.settings.child(self._hw_settings_name, *path).setValue(data)
        except Exception:
            pass
        finally:
            self._syncing_from_hw = False

    def _module_value_changed(self, param: 'Parameter'):
        """Forward hw_settings edits from this module to the hardware thread.

        Per-controller params are also mirrored to the shared _hw_settings so
        other subscribers (e.g. another axis on the same controller) stay in sync.
        Per-channel params (in _PER_CHANNEL_PARAMS) are not mirrored.
        """
        if getattr(self, '_syncing_from_hw', False):
            return
        if self._ct is not None:
            hw_subtree = self.settings.child(self._hw_settings_name)
            hw_path = hw_subtree.childPath(param)
            if hw_path is not None:
                self._settings_update.emit(hw_path, param.value(), 'value')
                if self._hw_settings is not None and not self._is_per_channel(hw_path):
                    with QSignalBlocker(self._hw_settings):
                        try:
                            self._hw_settings.child(*hw_path).setValue(param.value())
                        except Exception:
                            pass
