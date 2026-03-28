"""Base class shared by all PyMoDAQ hardware plugins.

``DAQ_Plugin_base`` consolidates the logic that was previously duplicated
between ``DAQ_Move_base`` and ``DAQ_Viewer_base``:

* Parameter-tree change propagation (``send_param_status``, ``update_settings``)
* Status emission (``emit_status``)
* Master/Slave controller initialization (``_init_controller``)
* Stub hooks (``commit_settings``, ``ini_attributes``)
* ``is_master`` property

It also adds the new capabilities API:

* ``capabilities_updated_signal`` / ``change_done_signal`` signals
* ``capabilities`` live property with lazy inference and setter
* ``query_data`` / ``change_to`` new-style hardware interface stubs
* ``_poll_until_done`` blocking convergence helper

Signal relay chain
------------------
::

    plugin.capabilities_updated_signal
        → DAQ_Move_Hardware.capabilities_updated_signal   (QueuedConnection)
        → DAQ_Move.capabilities_updated_signal            (QueuedConnection)
        → ModuleCompactDock._on_capabilities_updated      (QueuedConnection)

The ``QueuedConnection`` is **mandatory** because the signal can fire
from the hardware thread.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, ClassVar, Optional

from qtpy.QtCore import QObject, Signal, Slot
from qtpy.QtWidgets import QApplication
from easydict import EasyDict as edict

from pymodaq_utils.utils import ThreadCommand
from pymodaq_gui.parameter import Parameter
import pymodaq_gui.parameter.utils as putils

from pymodaq.control_modules.thread_commands import ThreadStatus, ControllerStatus

if TYPE_CHECKING:
    from pymodaq.control_modules.capabilities import Capabilities
    from pymodaq_data.data import DataToExport


__all__ = ['DAQ_Plugin_base']


class DAQ_Plugin_base(QObject):
    """Common base for all PyMoDAQ hardware plugin classes.

    Subclasses (``DAQ_Move_base``, ``DAQ_Viewer_base``) call
    ``QObject.__init__(self)`` themselves; this class does **not** call
    ``super().__init__()`` so that MRO chaining remains safe.

    Signals
    -------
    capabilities_updated_signal : Signal(object)
        Emitted with the new :class:`~pymodaq.control_modules.capabilities.Capabilities`
        whenever the plugin's capability set changes.  Consumers **must**
        connect with ``Qt.ConnectionType.QueuedConnection`` because this
        signal may fire from a hardware thread.
    change_done_signal : Signal(str, object)
        Emitted when a ``change_to`` operation completes.  Carries
        ``(channel_name, DataToExport | None)``.
    """

    #: Class-level sentinel detected by the relay-wiring code.
    _new_style_plugin: ClassVar[bool] = True

    #: Fallback title used when no *parent* worker is provided at construction.
    #: Override in subclasses (e.g. ``"myactuator"`` / ``"mydetector"``).
    _default_title: ClassVar[str] = 'myplugin'

    #: Plugin parameter definitions.  Subclasses populate this at class level.
    params: ClassVar[list] = []

    capabilities_updated_signal = Signal(object)   # Capabilities
    change_done_signal = Signal(str, object)        # (channel_name, DataToExport | None)

    # ------------------------------------------------------------------
    # Shared __init__ — settings tree, parent, title, controller
    # ------------------------------------------------------------------

    def __init__(self, parent=None, params_state=None) -> None:
        """Initialise the settings tree and shared plugin state.

        Subclasses call ``QObject.__init__(self)`` *before* calling
        ``super().__init__(parent, params_state)`` (or inline the body), since
        ``QObject.__init__`` must be the first call on the MRO.

        Parameters
        ----------
        parent :
            The hardware worker object (``DAQ_Move_Hardware`` /
            ``DAQ_Detector``).  Provides ``title`` and ``status_sig``.
        params_state :
            Saved parameter state to restore, either as a ``dict`` or a
            :class:`~pymodaq_gui.parameter.Parameter` instance.
        """
        self.parent_parameters_path: list = []
        self.settings = Parameter.create(
            name='Settings', type='group', children=self.params
        )
        if params_state is not None:
            if isinstance(params_state, dict):
                self.settings.restoreState(params_state)
            elif isinstance(params_state, Parameter):
                self.settings.restoreState(params_state.saveState())

        self.settings.sigTreeStateChanged.connect(self.send_param_status)

        self.parent = parent
        self._title: str = parent.title if parent is not None else self._default_title
        self.controller = None
        self.status = edict(info="", controller=None, initialized=False)

    # ------------------------------------------------------------------
    # Parameter-tree infrastructure (shared between move and viewer)
    # ------------------------------------------------------------------

    def emit_status(self, status: ThreadCommand) -> None:
        """Emit *status* back to the main GUI via the parent worker's signal.

        If ``self.parent`` is not set (standalone / test use) the status is
        printed to stdout instead.
        """
        if self.parent is not None:
            self.parent.status_sig.emit(status)
            QApplication.processEvents()
        else:
            print(status)

    def ini_attributes(self) -> None:
        """Override in subclasses to initialise plugin-specific attributes."""

    def commit_settings(self, param: Parameter) -> None:
        """Override to push a single parameter change to the hardware."""

    def send_param_status(self, param, changes) -> None:
        """Forward parameter-tree changes to the main GUI.

        Connected to ``self.settings.sigTreeStateChanged``.  Each change is
        packed into an ``UPDATE_SETTINGS`` :class:`~pymodaq_utils.utils.ThreadCommand`
        and sent via :meth:`emit_status`.
        """
        for param, change, data in changes:
            path = self.settings.childPath(param)
            if change == 'childAdded':
                self.emit_status(ThreadCommand(
                    ThreadStatus.UPDATE_SETTINGS,
                    [self.parent_parameters_path + path,
                     [data[0].saveState(), data[1]],
                     change],
                ))
            elif change in ('value', 'limits', 'options'):
                self.emit_status(ThreadCommand(
                    ThreadStatus.UPDATE_SETTINGS,
                    [self.parent_parameters_path + path, data, change],
                ))
            # 'parent' (removal) is intentionally ignored here

    @Slot(edict)
    def update_settings(self, settings_parameter_dict: edict) -> None:
        """Apply a settings change arriving from the main GUI.

        Temporarily disconnects ``send_param_status`` to avoid echo,
        applies the tree mutation, reconnects, then calls
        :meth:`_apply_settings` so subclasses can push changes to hardware.

        Parameters
        ----------
        settings_parameter_dict :
            ``edict`` with keys ``path``, ``param``, ``change``.
        """
        path = settings_parameter_dict['path']
        param = settings_parameter_dict['param']
        change = settings_parameter_dict['change']
        apply_settings = True
        try:
            self.settings.sigTreeStateChanged.disconnect(self.send_param_status)
        except Exception:
            pass
        if change == 'value':
            self.settings.child(*path[1:]).setValue(param.value())
        elif change == 'childAdded':
            try:
                child = Parameter.create(name='tmp')
                # param may be either a Parameter object or a pre-serialised
                # state dict depending on which side sends the signal.
                state = param.saveState() if hasattr(param, 'saveState') else param
                child.restoreState(state)
                self.settings.child(*path[1:]).addChild(child)
                param = child
            except (ValueError, Exception):
                apply_settings = False
        elif change == 'parent':
            try:
                children = putils.get_param_from_name(self.settings, param.name())
                if children is not None:
                    path = putils.get_param_path(children)
                    self.settings.child(*path[1:-1]).removeChild(children)
            except (IndexError, Exception):
                pass
        self.settings.sigTreeStateChanged.connect(self.send_param_status)
        if apply_settings:
            self._apply_settings(param)

    def _apply_settings(self, param: Parameter) -> None:
        """Called by :meth:`update_settings` after the tree mutation.

        The default implementation calls :meth:`commit_settings`.
        ``DAQ_Move_base`` overrides this to also call
        ``commit_common_settings`` and handle ``axis``/``epsilon`` params.
        """
        self.commit_settings(param)

    # ------------------------------------------------------------------
    # Master / Slave controller initialisation
    # ------------------------------------------------------------------

    @property
    def is_master(self) -> bool:
        """True when this plugin instance owns the shared hardware controller."""
        return self.settings['controller', 'controller_status'] == ControllerStatus.MASTER

    def _init_controller(
        self,
        old_controller=None,
        new_controller=None,
        slave_controller=None,
    ):
        """Manage the Master/Slave controller assignment.

        Call from ``ini_stage`` / ``ini_detector`` before opening hardware.
        Resets ``self.status``, assigns ``self.controller``, and returns the
        controller object to use.

        Parameters
        ----------
        old_controller :
            Controller from a previously initialised plugin instance
            (deprecated spelling; prefer *slave_controller*).
        new_controller :
            Freshly created controller instance (Master path).
        slave_controller :
            Controller from a previously initialised plugin instance
            (preferred spelling for the Slave path).

        Returns
        -------
        object
            The controller to use for this instance.

        Raises
        ------
        Exception
            If this instance is a Slave but no external controller was given.
        """
        if old_controller is None and slave_controller is not None:
            old_controller = slave_controller
        self.status.update(edict(info="", controller=None, initialized=False))
        if not self.is_master:
            if old_controller is None:
                raise Exception(
                    'no controller has been defined externally while this '
                    'axis is a slave one'
                )
            controller = old_controller
        else:
            controller = new_controller
        self.controller = controller
        return controller

    # ------------------------------------------------------------------
    # Capabilities property
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> 'Capabilities':
        """Return the plugin's current :class:`~pymodaq.control_modules.capabilities.Capabilities`.

        The default implementation lazily infers capabilities from the
        class via :func:`~pymodaq.control_modules.capabilities.infer_capabilities`
        and caches the result.  Subclasses may override to return a
        static class-level ``Capabilities`` object directly.
        """
        caps = self.__dict__.get('_capabilities')
        if caps is not None:
            return caps
        # Guard against re-entrant calls: infer_capabilities does
        # getattr(plugin, 'capabilities', None) which would re-enter this
        # property.  The flag causes the recursive call to return None, which
        # infer_capabilities treats as "not a Capabilities" and falls through
        # to its heuristic logic.
        if self.__dict__.get('_caps_computing'):
            return None
        self.__dict__['_caps_computing'] = True
        try:
            from pymodaq.control_modules.capabilities import infer_capabilities
            result = infer_capabilities(self)
            self.__dict__['_capabilities'] = result
            return result
        finally:
            self.__dict__['_caps_computing'] = False

    @capabilities.setter
    def capabilities(self, new_caps: 'Capabilities') -> None:
        """Set capabilities and emit :attr:`capabilities_updated_signal`."""
        self._capabilities = new_caps
        self.capabilities_updated_signal.emit(new_caps)

    # ------------------------------------------------------------------
    # New-style hardware interface stubs
    # ------------------------------------------------------------------

    def query_data(self, names=None, fresh: bool = True) -> 'DataToExport':
        """Return current values as a :class:`~pymodaq_data.data.DataToExport`.

        Raises
        ------
        NotImplementedError
            Subclasses that advertise new-style capabilities must override.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement query_data()"
        )

    def change_to(self, name: str, value) -> None:
        """Apply *value* to the channel identified by *name*.

        Raises
        ------
        NotImplementedError
            Subclasses that advertise new-style capabilities must override.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement change_to()"
        )

    # ------------------------------------------------------------------
    # Polling helper
    # ------------------------------------------------------------------

    def _poll_until_done(
        self,
        name: str,
        target,
        epsilon: float,
        timeout: float = 10.0,
        poll_interval: float = 0.05,
    ) -> bool:
        """Block until the channel value is within *epsilon* of *target*.

        Emits :attr:`change_done_signal` when the condition is met or the
        timeout expires.

        Returns
        -------
        bool
            ``True`` if converged within *timeout*; ``False`` otherwise.
        """
        deadline = time.perf_counter() + timeout
        dte = None
        while time.perf_counter() < deadline:
            try:
                dte = self.query_data(names=[name], fresh=True)
                dwa = dte.data[0] if dte.data else None
                if dwa is not None:
                    actual = float(dwa.data[0].flat[0])
                    if abs(actual - target) <= epsilon:
                        self.change_done_signal.emit(name, dte)
                        return True
            except Exception:
                pass
            time.sleep(poll_interval)
        self.change_done_signal.emit(name, dte)
        return False
