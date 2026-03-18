"""
LECO Director instrument plugin are to be used to communicate (and control) remotely real
instrument plugin through TCP/IP using the LECO Protocol

For this to work a coordinator must be instantiated can be done within the dashboard or directly
running: `python -m pyleco.coordinators.coordinator`

"""

import numpy as np

from typing import Optional, Union

from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun, main,
                                                          DataActuatorType, DataActuator)
from pymodaq.control_modules.thread_commands import ThreadStatus, ThreadStatusMove

from pymodaq_utils.utils import ThreadCommand
from pymodaq_utils.utils import find_dict_in_list_from_key_val
from serializall import SerializableFactory
from pymodaq_gui.parameter import Parameter

from pymodaq.utils.leco.leco_director import (LECODirector, leco_parameters, DirectorCommands,
                                              DirectorReceivedCommands)
from pymodaq.utils.leco.director_utils import ActuatorDirector, PymodaqMoveDirector

from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))


class DAQ_Move_LECODirector(LECODirector, DAQ_Move_base):
    """A control module, which in the dashboard, allows to control a remote Move module.

        ================= ==============================
        **Attributes**      **Type**
        *command_server*    instance of Signal
        *x_axis*            1D numpy array
        *y_axis*            1D numpy array
        *data*              double precision float array
        ================= ==============================

        See Also
        --------
        utility_classes.DAQ_TCP_server
    """
    settings: Parameter
    controller: Optional[Union[ActuatorDirector, PymodaqMoveDirector]]
    _axis_names = ['']
    _controller_units = ['']
    _epsilon = 1

    params_client = []  # parameters of a client grabber
    data_actuator_type = DataActuatorType.DataActuator
    params = comon_parameters_fun(axis_names=_axis_names, epsilon=_epsilon) + leco_parameters + [
        {'title': 'Variable name:', 'name': 'variable_name', 'type': 'list',
         'limits': ['position'], 'value': 'position',
         'tip': 'Which variable (axis) this director controls. '
                'Populated automatically from actor capabilities on init or via "Query capabilities".'},
    ]

    for param_name in ('multiaxes', 'units', 'epsilon', 'bounds', 'scaling'):
        param_dict = find_dict_in_list_from_key_val(params, 'name', param_name)
        if param_dict is not None:
            param_dict['visible'] = False

    def __init__(
        self, parent=None, params_state=None, host: Optional[str] = None, port: Optional[int] = None, **kwargs
    ) -> None:
        DAQ_Move_base.__init__(self, parent=parent, params_state=params_state)
        if host is not None:
            self.settings["host"] = host
        if port is not None:
            self.settings["port"] = port
        LECODirector.__init__(self, host=self.settings["host"], port=self.settings["port"])
        self.register_rpc_methods((
            self.set_units,  # to set units accordingly to the one of the actor
            self.on_acquisition_status,
        ))

        self.register_binary_rpc_methods((
            self.send_position,  # to display the actor position
            self.set_move_done,  # to set the move as done
        ))
        self.start_timer()
        # Connect ZMQ data-channel messages (new actor path) to local handler.
        # data_signal is dedicated to ZMQ frames so high-rate data never blocks
        # control commands (stop_grab etc.) queued on cmd_signal.
        self.listener.signals.data_signal.connect(self._on_actor_data)
        # To distinguish how to encode positions, it needs to now if it deals
        # with a json-accepting or a binary-accepting actuator
        # It is set to False by default. It then use the first received message
        # from the actuator that should contain its position to decide if it
        # need to switch to json.
        self.json = False

    def ini_stage(self, controller=None):
        """Actuator communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        actor_name = self.settings["actor_name"]

        if self.is_master:
            if self.settings['use_legacy_actor']:
                self.controller = ActuatorDirector(actor=actor_name, communicator=self.communicator)
                try:
                    self.controller.set_remote_name(self.communicator.full_name)
                except TimeoutError:
                    logger.warning("Timeout setting remote name.")
                self.json = False
                self.controller.get_settings()
            else:
                self.controller = PymodaqMoveDirector(actor=actor_name, communicator=self.communicator)
                try:
                    caps = self.controller.get_capabilities()
                    var_names = [v.name for v in caps.variables] or ['position']
                    # Set epsilon from capabilities for accurate move-done detection.
                    var_name_sel = self.settings['variable_name'] or var_names[0]
                    var_caps = next(
                        (v for v in caps.variables if v.name == var_name_sel), None
                    )
                    if var_caps is None and var_names:
                        var_caps = caps.variables[0] if caps.variables else None
                    if var_caps is not None and hasattr(var_caps, 'epsilon') and var_caps.epsilon > 0:
                        self._epsilon = var_caps.epsilon
                except Exception:
                    var_names = ['position']
                    logger.warning("Could not fetch capabilities; defaulting variable name to 'position'.")
                # Populate the variable_name list with what this actor actually exposes.
                self._apply_variable_names(var_names)
                try:
                    self.controller.subscribe_settings()
                except Exception:
                    logger.warning("Timeout during subscribe_settings.")
                # Subscribe to the per-channel sub-topic: "{actor_pub_topic}/{var_name}".
                try:
                    self._actor_full_name = self.controller.get_actor_pub_topic()
                except Exception:
                    _namespace = self.communicator.namespace
                    self._actor_full_name = f"{_namespace}.{actor_name}" if _namespace else actor_name
                    logger.warning(
                        "Could not fetch actor pub topic via RPC; "
                        "falling back to '%s'.", self._actor_full_name
                    )
                var_name = self.settings['variable_name'] or 'position'
                self._actor_sub_name = f"{self._actor_full_name}/{var_name}"
                try:
                    self.listener.subscribe(self._actor_sub_name)
                except Exception:
                    logger.warning("Could not subscribe to actor ZMQ data channel.")
                # Start continuous position subscription (low rate) for always-fresh readback.
                try:
                    self.controller.query_data(
                        names=[var_name], count=float('inf'), fresh=True, period=0.05
                    )
                except Exception:
                    logger.warning("Could not start continuous position subscription.")
        else:
            self.controller = controller

        info = f"LECODirector: {self._title} is initialized"
        initialized = True
        return info, initialized

    def move_abs(self, position: DataActuator) -> None:
        position = self.check_bound(position)
        position = self.set_position_with_scaling(position)
        self.target_value = position
        if self.settings['use_legacy_actor']:
            if self.json:
                if hasattr(self, 'shape') and self.shape == ():
                    position = position.value(self.axis_unit)
                else:
                    position = np.full(self.shape, position.value(self.axis_unit)).tolist()
            self.controller.move_abs(position=position)
        else:
            var_name = self.settings['variable_name'] or 'position'
            self.controller.change_to(var_name, position.value(self.axis_unit))

    def move_rel(self, position: DataActuator) -> None:
        position = self.check_bound(self.current_value + position) - self.current_value  # type: ignore  # noqa
        self.target_value = position + self.current_value
        position = self.set_position_relative_with_scaling(position)
        if self.settings['use_legacy_actor']:
            if self.json:
                if hasattr(self, 'ndim') and self.shape == ():
                    position = position.value(self.axis_unit)
                else:
                    position = np.full(self.shape, position.value(self.axis_unit)).tolist()
            self.controller.move_rel(position=position)
        else:
            var_name = self.settings['variable_name'] or 'position'
            self.controller.change_to(var_name, position.value(self.axis_unit))

    def move_home(self):
        if self.settings['use_legacy_actor']:
            self.controller.move_home()
        else:
            var_name = self.settings['variable_name'] or 'position'
            self.controller.change_to(var_name, 0.0)

    def get_actuator_value(self) -> DataActuator:
        """Get the current hardware value.

        Triggers a fresh actor read (non-legacy path) or a legacy RPC call.
        The actual value arrives asynchronously via ``_on_actor_data`` /
        ``send_position``.  If the actor is unreachable the cached
        ``_current_value`` is returned without raising, so ``DAQ_Move.ini_stage``
        is not aborted by a transient coordinator timeout.
        """
        try:
            if self.settings['use_legacy_actor']:
                self.controller.get_actuator_value()
            else:
                # _current_value is kept current by the continuous ZMQ stream started
                # in ini_stage.  A fresh=False query publishes the cached value — fast,
                # no hardware access needed.
                self.controller.query_data(names=None, count=1, fresh=False)
        except Exception:
            logger.warning("get_actuator_value: could not reach actor, returning cached value.")
        return self._current_value

    def stop_motion(self) -> None:
        if self.settings['use_legacy_actor']:
            self.controller.stop_motion()
        # else: no equivalent stop in new API yet

    def _on_actor_data(self, topic: str, dte) -> None:
        """Handle data published by the PymodaqActor on the ZMQ data channel.

        The director is subscribed to ``"{actor}/{variable_name}"`` so only
        frames for this channel arrive here — no name filtering needed.
        Called when ``use_legacy_actor=False``.
        """
        if dte is None:
            return
        try:
            dwa = dte.data[0]   # sub-topic DTE always carries exactly one DWA
            pos_val = float(dwa.data[0].ravel()[0])
            pos = DataActuator(data=[np.atleast_1d(np.array([pos_val]))])
            pos = self.get_position_with_scaling(pos)
            self._current_value = pos
            self.emit_status(ThreadCommand(ThreadStatusMove.GET_ACTUATOR_VALUE, pos))
        except Exception:
            logger.warning("_on_actor_data: could not extract position from DataToExport.")

    # Methods accessible via remote calls
    def _set_position_value(
        self, data: Union[dict, list, str, float, None], additional_payload=None
    ) -> DataActuator:

        # This is the first received message, if position is set then
        # it's included in the json payload and the director should
        # usejson


        if data is not None:
            position = data.get('position', [])

            self.shape = np.array(position).shape
            position = [np.atleast_1d(position)]

            pos = DataActuator(data=position)
            self.json = True
        elif additional_payload:
            pos = SerializableFactory().get_apply_deserializer(additional_payload[0])
        else:
            raise ValueError("No position given")
        pos = self.get_position_with_scaling(pos)  # type: ignore
        self._current_value = pos
        return pos

    def send_position(self, data: Union[dict, list, str, float, None], additional_payload=None) -> None:
        pos = self._set_position_value(data=data, additional_payload=additional_payload)
        self.emit_status(ThreadCommand(ThreadStatusMove.GET_ACTUATOR_VALUE, pos))

    def set_move_done(self, data: Union[dict, list, str, float, None], additional_payload=None) -> None:
        pos = self._set_position_value(data=data, additional_payload=additional_payload)
        self.emit_status(ThreadCommand(ThreadStatusMove.MOVE_DONE, pos))

    def set_units(self, units: str, additional_payload=None) -> None:
        if units not in self.axis_units:
            self.axis_units.append(units)
        self.axis_unit = units

    def set_director_settings(self, settings: bytes):
        """ Get the content of the actor settings to pe populated in this plugin
        'settings_client' parameter

        Then set the plugin units from this information"""
        super().set_director_settings(settings)
        self.axis_unit = self.settings['settings_client', 'units']

    # ── Capability refresh ─────────────────────────────────────────────────────

    def value_changed(self, param) -> None:
        if param.name() == 'variable_name' and getattr(self, '_actor_full_name', None):
            new_var = param.value() or 'position'
            new_topic = f"{self._actor_full_name}/{new_var}"
            if new_topic != self._actor_sub_name:
                try:
                    self.listener.unsubscribe(self._actor_sub_name)
                    self.listener.subscribe(new_topic)
                    self._actor_sub_name = new_topic
                except Exception:
                    logger.warning("Could not update ZMQ subscription for variable change.")

    def commit_leco_settings(self, param) -> None:
        super().commit_leco_settings(param)
        if param.name() == 'query_caps':
            self._query_and_apply_capabilities()

    def _query_and_apply_capabilities(self) -> None:
        """Ask the actor for its capabilities and update the variable_name selector."""
        if self.settings['use_legacy_actor']:
            logger.info("Capability query only supported with use_legacy_actor=False.")
            return
        actor_name = self.settings['actor_name']
        try:
            tmp = PymodaqMoveDirector(actor=actor_name, communicator=self.communicator)
            caps = tmp.get_capabilities()
            var_names = [v.name for v in caps.variables] or ['position']
            self._apply_variable_names(var_names)
            logger.info("Capabilities refreshed from actor '%s': variables=%s", actor_name, var_names)
        except Exception as exc:
            logger.warning("Could not query capabilities from actor '%s': %s", actor_name, exc)

    def _apply_variable_names(self, var_names: list) -> None:
        current = self.settings['variable_name']
        self.settings.child('variable_name').setLimits(var_names)
        if current not in var_names:
            self.settings.child('variable_name').setValue(var_names[0])

    def on_acquisition_status(self, read_list: dict, is_grabbing: bool) -> None:
        """Invoked by the actor when its acquisition status changes.

        Allows this director's GUI to mirror the grab state of the actor
        even when the grab was initiated by a different director.

        Parameters
        ----------
        read_list:
            Current read_list dict from the actor.
        is_grabbing:
            ``True`` while the actor has at least one active read request.
        """
        self.emit_status(ThreadCommand('ACQUISITION_STATUS', {
            'read_list': read_list,
            'is_grabbing': is_grabbing,
        }))

    def close(self) -> None:
        """Clear the content of the settings_clients setting."""
        self.timer.stop()
        if not self.settings['use_legacy_actor'] and self.controller is not None:
            var_name = self.settings['variable_name'] or None
            try:
                self.controller.stop(names=[var_name] if var_name else None)
            except Exception:
                pass
            try:
                self.controller.unsubscribe_settings()
            except Exception:
                pass
            try:
                self.listener.unsubscribe(getattr(self, '_actor_sub_name', self.settings['actor_name']))
            except Exception:
                pass
        super().close()



if __name__ == '__main__':
    main(__file__, init=False)
