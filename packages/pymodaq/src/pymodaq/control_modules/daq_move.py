# -*- coding: utf-8 -*-
"""
Created the 29/07/2022

@author: Sebastien Weber
"""

from __future__ import annotations

import numbers
from importlib import import_module
from numbers import Number

import sys
from typing import List, Union, Optional, Dict, TypeVar, TYPE_CHECKING
import numpy as np

from qtpy.QtCore import QObject, Signal, QThread, Slot, QTimer

from easydict import EasyDict as edict

from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils.utils import find_keys_from_val
from pymodaq_utils import utils
from pymodaq.utils.gui_utils import get_splash_sc
from pymodaq_utils import config as config_mod
from pymodaq.utils.exceptions import ActuatorError
from pymodaq_utils.warnings import deprecation_msg
from pymodaq.utils.data import DataToExport, DataActuator
from pymodaq_data.h5modules.backends import Node

from pymodaq_gui.h5modules.saving import H5Saver
from pymodaq_gui.parameter import Parameter
from pymodaq_gui.parameter import utils as putils
from pymodaq_gui.qt_utils import mkQApp

from pymodaq.utils.h5modules import module_saving
from pymodaq.control_modules.instruments import ACTUATOR_TYPES, ACTUATOR_NAMES, get_actuator_plugin
from pymodaq.control_modules.utils import ParameterControlModule, HardwareWorker
from pymodaq.control_modules.daq_move_ui.actuator_selector import SelectedActuator

from pymodaq.control_modules.thread_commands import (ThreadStatus, ThreadStatusMove, ControlToHardwareMove,
                                                     UiToMainMove,
                                                     )
from pymodaq.control_modules.move_utility_classes import (ThreadCommand, MoveCommand, DAQ_Move_base, DataActuatorType,
                                                           check_units)

from pymodaq.control_modules.move_utility_classes import params as daq_move_params
from pymodaq.utils.leco.pymodaq_listener import (MoveActorListener, LECOMoveCommands)
from pymodaq.control_modules.utils import ControllerStatus
from pymodaq import Q_, Unit


from pymodaq.control_modules.daq_move_ui.factory import ActuatorUIFactory
from pymodaq.utils.config import Config as ControlModulesConfig

if TYPE_CHECKING:
    from pymodaq.control_modules.daq_move_ui.ui_base import DAQ_Move_UI_Base

local_path = config_mod.get_set_local_dir()
sys.path.append(str(local_path))
logger = set_logger(get_module_name(__file__))

config_utils = config_mod.Config()
config = ControlModulesConfig()

HardwareController = TypeVar("HardwareController")


STATUS_WAIT_TIME = 1000


class DAQ_Move(ParameterControlModule):
    """Main PyMoDAQ class to drive actuators

    Qt object and generic UI to drive actuators.

    Attributes
    ----------
    init_signal: Signal[bool]
        This signal is emitted when the chosen actuator is correctly initialized
    move_done_signal: Signal[str, DataActuator]
        This signal is emitted when the chosen actuator finished its action. It gives the actuator's name and current
        value
    bounds_signal: Signal[bool]
        This signal is emitted when the actuator reached defined limited boundaries.

    See Also
    --------
    :class:`ControlModule`, :class:`ParameterManager`
    """

    settings_name = "daq_move_settings"

    move_done_signal = Signal(DataActuator)
    current_value_signal = Signal(DataActuator)
    bounds_signal = Signal(bool)

    params = daq_move_params +  [
        {'title': 'Saver Settings:', 'name': 'saver_settings', 'type': 'group',
         'visible': False, 'children': H5Saver.params}]

    listener_class = MoveActorListener
    ui: Optional[DAQ_Move_UI_Base]

    @property
    def _plugin_settings_name(self) -> str:
        """Return the name of the plugin settings parameter group."""
        return 'move_settings'

    @property
    def _component_name(self) -> str:
        """Return the component name."""
        return 'actuator'

    def _get_plugin_class_and_params(self):
        """Get the actuator plugin class and parameters."""
        return get_actuator_plugin(self._actuator)

    def _update_main_settings_on_component_change(self, component):
        """Update move_type setting when actuator changes."""
        self.settings.child("main_settings", "move_type").setValue(component)

    @property
    def _saver_class(self):
        """Return the saver class to use for this control module."""
        return module_saving.ActuatorTimeSaver

    @property
    def _close_command(self) -> str:
        """Return the close command enum value."""
        return ControlToHardwareMove.CLOSE

    def _create_hardware_instance(self):
        """Factory method - create hardware instance."""
        return DAQ_Move_Hardware(
            self._actuator, self._current_value, self._title
        )

    def _emit_init_command(self):
        """Emit initialization command to hardware."""
        self.command_hardware.emit(
            ThreadCommand(
                ControlToHardwareMove.INI_STAGE,
                attribute=[
                    self.settings.child("move_settings").saveState(),
                    self.controller,
                ],
            )
        )

    def _set_ui_init_state(self, status: bool):
        """Set UI initialization state."""
        if self.ui is not None:
            self.ui.actuator_init = status

    def __init__(
        self, parent=None, title="DAQ Move", ui_identifier: Optional[str] = None, **kwargs
    ) -> None:
        """

        Parameters
        ----------
        parent: QWidget or None
        parent: QWidget or None
            if it is a valid QWidget, it will hold the user interface to drive it
        title: str
            The unique (should be unique) string identifier for the underlying actuator
        """

        self.logger = set_logger(f"{logger.name}.{title}")
        self.logger.info(f"Initializing DAQ_Move: {title}")

        super().__init__(action_list=("save", "update"), **kwargs)

        self._actuator: SelectedActuator = SelectedActuator()
        if not (
            ui_identifier is not None and ui_identifier in ActuatorUIFactory.keys()
        ):
            ui_identifier = config("actuator", "ui")[0]
        self.settings.child("main_settings", "ui_type").setValue(ui_identifier)
        self.settings.child("main_settings", "ui_type").setOpts(readonly=True)

        DAQ_Move_UI = ActuatorUIFactory.get(ui_identifier)

        self.parent = parent
        if parent is not None:
            self.ui = DAQ_Move_UI(parent, title, self.settings_tree)
        else:
            self.ui = None

        if self.ui is not None:
            self.ui.actuators = ACTUATOR_NAMES
            self.ui.command_sig.connect(self.process_ui_cmds)

        self.splash_sc = get_splash_sc()
        self._title = title



        self._module_and_data_saver: module_saving.ActuatorTimeSaver = None
        self._hide_saver_params()

        self._move_done_bool = True
        self.actuator = self._actuator

        self._current_value = DataActuator(title, units=self.units)
        self._target_value = DataActuator(title, units=self.units)
        self._relative_value = DataActuator(title, units=self.units)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.get_actuator_value)



    def process_ui_cmds(self, cmd: utils.ThreadCommand):
        """Process commands sent by actions done in the ui

        Parameters
        ----------
        cmd: ThreadCommand
            Possible values are :
            * init
            * get_value
            * loop_get_value
            * find_home
            * stop
            * move_abs
            * move_rel
            * actuator_changed
            * rel_value
        """
        if cmd.command == UiToMainMove.INIT:
            self.init_hardware(cmd.attribute[0])
        elif cmd.command == UiToMainMove.GET_VALUE:
            self.get_actuator_value()
        elif cmd.command == UiToMainMove.LOOP_GET_VALUE:
            self.get_continuous_actuator_value(cmd.attribute)
        elif cmd.command == UiToMainMove.FIND_HOME:
            self.move_home()
        elif cmd.command == UiToMainMove.STOP:
            self.stop_motion()
        elif cmd.command == UiToMainMove.MOVE_ABS:
            data_act: DataActuator = cmd.attribute
            if (
                not Unit(data_act.units).is_compatible_with(self.units)
                and data_act.units != ""
            ):
                data_act.force_units(self.units)
            self.move_abs(data_act)
        elif cmd.command == UiToMainMove.MOVE_REL:
            data_act: DataActuator = cmd.attribute
            if (
                not Unit(data_act.units).is_compatible_with(self.units)
                and data_act.units != ""
            ):
                data_act.force_units(self.units)
            self.move_rel(data_act)
            self.ui.config = self.config
        elif cmd.command == UiToMainMove.ACTUATOR_CHANGED:
            if isinstance(cmd.attribute, SelectedActuator):
                self._update_selected_component(cmd.attribute, from_ui=True)
        elif cmd.command == UiToMainMove.REL_VALUE:
            self._relative_value = cmd.attribute


    def append_data(
        self, dte: Optional[DataToExport] = None, where: Union[Node, str, None] = None
    ):
        """Appends current DataToExport to an ActuatorEnlargeableSaver

        Parameters
        ----------
        dte: DataToExport, optional
        where: Node or str
        See Also
        --------
        ActuatorEnlargeableSaver
        """
        if dte is None:
            dte = DataToExport(name=self.title, data=[self._current_value])
        self._add_data_to_saver(dte, where=where)
        self.settings.child('saver_settings', 'N_saved').setValue(self.settings['saver_settings', 'N_saved'] + 1)

    def _add_data_to_saver(self, data: DataToExport, where=None, **kwargs):
        """Adds DataToExport data to the current node using the declared module_and_data_saver

        Filters the data to be saved by DataSource as specified in the current H5Saver (see self.module_and_data_saver)

        Parameters
        ----------
        data: DataToExport
            The data to be saved
        kwargs: dict
            Other named parameters to be passed as is to the module_and_data_saver

        See Also
        --------
        DetectorSaver, DetectorEnlargeableSaver, DetectorExtendedSaver

        """
        # todo: test this for logging

        node = self.module_and_data_saver.get_set_node(where)
        self.module_and_data_saver.add_data(node, data, **kwargs)

    def stop_motion(self):
        """Stop any motion"""
        try:
            self.command_hardware.emit(ThreadCommand(ControlToHardwareMove.STOP_MOTION))
        except Exception as e:
            self.logger.exception(str(e))

    def move(self, move_command: MoveCommand):
        """Generic method to trigger the correct action on the actuator

        Parameters
        ----------
        move_command: MoveCommand
            MoveCommand with move_type attribute either:
            * 'abs': performs an absolute action
            * 'rel': performs a relative action
            * 'home': find the actuator's home

        See Also
        --------
        :meth:`move_abs`, :meth:`move_rel`, :meth:`move_home`, :class:`..utility_classes.MoveCommand`

        """
        if move_command.move_type == "abs":
            self.move_abs(move_command.value)
        elif move_command.move_type == "rel":
            self.move_rel(move_command.value)
        elif move_command.move_type == "home":
            self.move_home(move_command.value)

    def move_abs(self, value: Union[DataActuator, numbers.Number], send_to_tcpip=False):
        """Move the connected hardware to the absolute value

        Returns nothing but the move_done_signal will be send once the action is done

        Parameters
        ----------
        value: ndarray
            The value the actuator should reach
        send_to_tcpip: bool
            if True, this position is send through the TCP/IP communication canal
        """
        try:
            if isinstance(value, Number):
                value = DataActuator(
                    self.title, data=[np.array([value])], units=self.units
                )
            self._send_to_tcpip = send_to_tcpip
            if value != self._current_value:
                if self.ui is not None:
                    self.ui.move_done = False
                self._move_done_bool = False
                self._target_value = value
                self.update_status("Moving")
                self.command_hardware.emit(
                    ThreadCommand(ControlToHardwareMove.RESET_STOP_MOTION)
                )
                self.command_hardware.emit(
                    ThreadCommand(ControlToHardwareMove.MOVE_ABS, attribute=[value])
                )

        except Exception as e:
            self.logger.exception(str(e))

    def move_home(self, send_to_tcpip=False):
        """Move the connected actuator to its home value (if any)

        Parameters
        ----------
        send_to_tcpip: bool
            if True, this position is send through the TCP/IP communication canal
        """
        self._send_to_tcpip = send_to_tcpip
        try:
            if self.ui is not None:
                self.ui.move_done = False
            self._move_done_bool = False
            self.update_status("Moving")
            self.command_hardware.emit(
                ThreadCommand(ControlToHardwareMove.RESET_STOP_MOTION)
            )
            self.command_hardware.emit(ThreadCommand(ControlToHardwareMove.MOVE_HOME))

        except Exception as e:
            self.logger.exception(str(e))

    def move_rel(
        self, rel_value: Union[DataActuator, numbers.Number], send_to_tcpip=False
    ):
        """Move the connected hardware to the relative value

        Returns nothing but the move_done_signal will be send once the action is done

        Parameters
        ----------
        value: float
            The relative value the actuator should reach
        send_to_tcpip: bool
            if True, this position is send through the TCP/IP communication canal
        """

        try:
            if isinstance(rel_value, Number):
                rel_value = DataActuator(
                    self.title, data=[np.array([rel_value])], units=self.units
                )
            self._send_to_tcpip = send_to_tcpip
            if self.ui is not None:
                self.ui.move_done = False
            self._move_done_bool = False
            self._target_value = self._current_value + rel_value
            self.update_status("Moving")
            self.command_hardware.emit(
                ThreadCommand(ControlToHardwareMove.RESET_STOP_MOTION)
            )
            self.command_hardware.emit(
                ThreadCommand(ControlToHardwareMove.MOVE_REL, attribute=[rel_value])
            )

        except Exception as e:
            self.logger.exception(str(e))

    def move_rel_p(self):
        self.move_rel(self._relative_value)

    def move_rel_m(self):
        self.move_rel(-self._relative_value)

    @property
    def initialized_state(self):
        """bool: status of the actuator's initialization (init or not)"""
        return self._initialized_state

    @property
    def move_done_bool(self):
        """bool: status of the actuator's status (done or not)"""
        return self._move_done_bool

    def value_changed(self, param: Parameter):
        """Apply changes of value in the settings"""
        result = super().value_changed(param=param)
        if result is None:
            return  # Already handled by base class

        if param.name() == "refresh_timeout":
            self._refresh_timer.setInterval(param.value())

        self._update_settings(param=param)

    def _init_continuous_save(self):
        """ Initialize the continuous saving H5Saver object

        Update the module_and_data_saver attribute as :class:`DetectorTimeSaver` object
        """
        if self.settings.child('saver_settings', 'do_save').value():

            self.settings.child('saver_settings', 'base_name').setValue('Data')
            self.settings.child('saver_settings', 'N_saved').show()
            self.settings.child('saver_settings', 'N_saved').setValue(0)
            self.h5saver.init_file(update_h5=True)
        else:
            self.settings.child('saver_settings', 'N_saved').hide()

    def _post_timeout_handling(self):
        self.wait_position_flag = False

    @Slot(ThreadCommand)
    def thread_status(
        self, status: ThreadCommand
    ):  # general function to get datas/infos from all threads back to the main
        """Get back info (using the ThreadCommand object) from the hardware

        And re-emit this ThreadCommand using the custom_sig signal if it should be used in a higher level module

        Commands valid for all control modules are defined in the parent class, here are described only the specific
        ones

        Parameters
        ----------
        status: ThreadCommand
            Possible values are:

            * **ini_stage**: obtains info from the initialization
            * **get_actuator_value**: update the UI current value
            * **move_done**: update the UI current value and emits the move_done signal
            * **outofbounds**: emits the bounds_signal signal with a True argument
            * **set_allowed_values**: used to change the behaviour of the spinbox controlling absolute values (see
              :meth:`daq_move_ui.set_abs_spinbox_properties`
            * stop: stop the motion
        """

        super().thread_status(status, "move")

        if status.command == ThreadStatusMove.INI_STAGE:
            self.update_status(
                f"Stage initialized: {status.attribute['initialized']} "
                f"info: {status.attribute['info']}"
            )
            if status.attribute["initialized"]:
                self.controller = status.attribute["controller"]
                self._set_ui_init_state(True)
                self._initialized_state = True
            else:
                self._initialized_state = False
            if self._initialized_state:
                self.get_actuator_value()
            self.init_signal.emit(self._initialized_state)

        elif (
            status.command == ThreadStatusMove.GET_ACTUATOR_VALUE
            or status.command == "check_position"
        ):
            data_act = self._check_data_type(status.attribute)
            if self.ui is not None:
                self.ui.display_value(data_act)
                if self.ui.has_action("show_graph") and self.ui.is_action_checked(
                    "show_graph"
                ):
                    self.ui.show_data(DataToExport(name=self.title, data=[data_act]))

            self._current_value = data_act
            if self.settings['saver_settings', 'do_save']:
                self.append_data()

            self.current_value_signal.emit(self._current_value)
            if self._send_to_tcpip:
                if self.settings.child("main_settings", "tcpip", "tcp_connected").value():
                    self._command_tcpip.emit(
                        ThreadCommand("position_is", data_act)
                        )
                if self.settings.child("main_settings", "leco", "leco_connected").value():
                    self._command_tcpip.emit(
                        ThreadCommand(LECOMoveCommands.POSITION, data_act)
                    )
        elif status.command == ThreadStatusMove.MOVE_DONE:
            data_act = self._check_data_type(status.attribute)
            if self.ui is not None:
                self.ui.display_value(data_act)
                self.ui.move_done = True
            self._current_value = data_act
            self._move_done_bool = True
            self.move_done_signal.emit(data_act)
            if self._send_to_tcpip:
                if self.settings.child("main_settings", "tcpip", "tcp_connected").value():
                    self._command_tcpip.emit(
                        ThreadCommand("move_done", data_act)
                        )
                if self.settings.child("main_settings", "leco", "leco_connected").value():
                    self._command_tcpip.emit(
                        ThreadCommand(LECOMoveCommands.MOVE_DONE, data_act)
                    )
        elif status.command == ThreadStatusMove.OUT_OF_BOUNDS:
            logger.warning(f"The Actuator {self.title} has reached its defined bounds")
            self.bounds_signal.emit(True)

        elif status.command == ThreadStatusMove.SET_ALLOWED_VALUES:
            if self.ui is not None:
                self.ui.set_abs_spinbox_properties(**status.attribute)

        elif status.command == ThreadStatusMove.STOP:
            self.stop_motion()

        elif status.command == ThreadStatusMove.UNITS:
            self.units = status.attribute

    def _check_data_type(
        self, data_act: Union[list, np.ndarray, Number, DataActuator]
    ) -> DataActuator:
        """Make sure the data is a DataActuator

        Mostly to make sure DAQ_Move is backcompatible with old style plugins
        """
        if isinstance(data_act, list):  # backcompatibility
            if isinstance(data_act[0], Number):
                data_act = DataActuator(
                    data=[np.atleast_1d(val) for val in data_act], units=self.units
                )
            elif isinstance(data_act[0], np.ndarray):
                data_act = DataActuator(data=data_act, units=self.units)
            elif isinstance(data_act[0], DataActuator):
                data_act = data_act[0]
            else:
                raise TypeError("Unknown data type")
        elif isinstance(data_act, np.ndarray):  # backcompatibility
            data_act = DataActuator(data=[data_act], units=self.units)
        data_act.name = (
            self.title
        )  # for the DataActuator name to be the title of the DAQ_Move
        if (
            not Unit(self.units).is_compatible_with(Unit(data_act.units))
            and data_act.units == ""
        ):  # this happens if the units have not been specified in
            # the plugin
            data_act.force_units(self.units)
        return data_act

    def get_actuator_value(self):
        """Get the current actuator value via the "get_actuator_value" command send to the hardware

        Returns nothing but the  `move_done_signal` will be send once the action is done
        """
        try:
            self.command_hardware.emit(
                ThreadCommand(ControlToHardwareMove.GET_ACTUATOR_VALUE)
            )

        except Exception as e:
            self.logger.exception(str(e))

    def grab(self):
        if self.ui is not None:
            self.manage_ui_actions("refresh_value", "setChecked", False)
        self.get_continuous_actuator_value(False)

    def stop_grab(self):
        """Stop value polling. Mandatory

        First uncheck the ui action if ui is not None, then stop the polling
        """
        if self.ui is not None:
            self.manage_ui_actions("refresh_value", "setChecked", False)
        self.get_continuous_actuator_value(False)

    def get_continuous_actuator_value(self, get_value=True):
        """Start the continuous getting of the actuator's value

        Parameters
        ----------
        get_value: bool
            if True start the timer to periodically fetch the actuator's value, else stop it

        Notes
        -----
        The current timer period is set by the refresh value *'refresh_timeout'* in the actuator main settings.
        """
        if get_value:
            self._refresh_timer.setInterval(
                self.settings["main_settings", "refresh_timeout"]
            )
            self._refresh_timer.start()
        else:
            self._refresh_timer.stop()

    @property
    def actuator(self):
        """Get/Set the currently selected actuator among available actuators"""
        return self._actuator

    @actuator.setter
    def actuator(self, act_type: SelectedActuator):
        if not isinstance(act_type, SelectedActuator):
            raise ActuatorError(
                f"{act_type} is an invalid actuator, should be within {ACTUATOR_NAMES}"
            )
        self._update_selected_component(act_type, from_ui=False)
        

    @property
    def actuators(self) -> List[str]:
        """Get the list of possible actuators"""
        return ACTUATOR_NAMES



    @property
    def units(self):
        """Get/Set the units for the controller"""
        return self.settings["move_settings", "units"]

    @units.setter
    def units(self, unit: str):
        self.settings.child("move_settings", "units").setValue(unit)
        if self.ui is not None and config("actuator", "display_units"):
            unit = self.get_unit_to_display(unit)
            self.ui.set_unit_as_suffix(unit)
            self.ui.set_unit_prefix(
                config("actuator", "siprefix")
                and (unit != "" or config("actuator", "siprefix_even_without_units"))
            )

    @property
    def axis_names(self) -> Union[List, Dict]:
        """ Get the names of all possible axis"""
        return self.settings.child('move_settings', 'controller', 'axis').opts['limits']

    @property
    def axis_name(self) -> str:
        """ Get/Set the current axis"""
        limits = self.settings.child('move_settings', 'controller', 'axis').opts['limits']
        val = self.settings['move_settings', 'controller', 'axis']
        if isinstance(limits, list):
            return val
        elif isinstance(limits, dict):
            return find_keys_from_val(limits, val=val)[0]
        else:
            TypeError('Unknown limits type')


    @axis_name.setter
    def axis_name(self, name: str):
        """ Get/Set the current axis"""
        limits = self.settings.child('move_settings', 'controller', 'axis').opts['limits']
        if name in limits:
            if isinstance(limits, list):
                value = name
            elif isinstance(limits, dict):
                value = limits[name]
            else:
                return
            self.settings.child('move_settings', 'controller', 'axis').setValue(value)

    @staticmethod
    def get_unit_to_display(unit: str) -> str:
        """Get the unit to be displayed in the UI

        If the controller units are in mm the displayed unit will be m
        because m is the base unit, then the user could ask for mm, km, µm...
        only issue is when the usual displayed unit is not the base one, then add cases below

        Parameters
        ----------
        unit: str

        Returns
        -------
        str: the unit to be displayed on the ui
        """
        if ("°" in unit or "degree" in unit) and not "°C" in unit:
            # special cas as pint base unit for angles are radians
            return "°"
        elif "°C" in unit:
            return "°C"
        else:
            for key in config("actuator", "allowed_units"):
                if key in unit:
                    return config("actuator", "allowed_units", key)
            return str(Q_(1, unit).to_base_units().units)

    def connect_tcp_ip(self):
        super().connect_tcp_ip(
            params_state=self.settings.child("move_settings"), client_type="ACTUATOR"
        )

    def connect_leco(self, connect: bool) -> None:
        super().connect_leco(connect)

    @Slot(ThreadCommand)
    def process_tcpip_cmds(self, status: ThreadCommand) -> None:
        if super().process_tcpip_cmds(status=status) is None:
            return
        if LECOMoveCommands.MOVE_ABS == status.command:
            self.move_abs(status.attribute, send_to_tcpip=True)

        elif LECOMoveCommands.MOVE_REL == status.command:
            self.move_rel(status.attribute, send_to_tcpip=True)

        elif LECOMoveCommands.MOVE_HOME == status.command:
            self.move_home(send_to_tcpip=True)

        elif "check_position" in status.command:
            deprecation_msg(
                "check_position is deprecated, you should use get_actuator_value"
            )
            self._send_to_tcpip = True
            self.get_actuator_value()

        elif LECOMoveCommands.GET_ACTUATOR_VALUE in status.command:
            self._send_to_tcpip = True
            self.get_actuator_value()

        elif status.command == LECOMoveCommands.STOP:
            self.stop_motion()


class DAQ_Move_Hardware(HardwareWorker):
    """Hardware worker class for actuator control.

    Attributes
    ----------
    hardware : DAQ_Move_base
        The actuator plugin instance
    actuator : SelectedActuator
        The selected actuator configuration
    hardware_adress : str
        Hardware address identifier
    axis_address : str
        Axis address identifier
    motion_stoped : bool
        Flag indicating if motion was stopped
    """

    def __init__(self, actuator, position: DataActuator, title="actuator"):
        super().__init__(title=title)
        self.actuator = actuator
        self.hardware_adress = None
        self.axis_address = None
        self.motion_stoped = False

    @property
    def _worker_type(self) -> str:
        """Return 'actuator' for logging."""
        return 'actuator'

    @property
    def _init_command_name(self) -> str:
        """Return the initialization command name."""
        return ControlToHardwareMove.INI_STAGE

    @property
    def _close_command_name(self) -> str:
        """Return the close command name."""
        return ControlToHardwareMove.CLOSE

    def _get_plugin_class_and_params(self, component):
        """Get the actuator plugin class and parameters."""
        return get_actuator_plugin(component)


    def get_actuator_value(self):
        """Get the current position checking the hardware value."""
        if self.hardware is not None:
            pos = self.hardware.get_actuator_value()
            if self.hardware.data_actuator_type == DataActuatorType.float:
                pos = DataActuator(self._title, data=pos, units=self.hardware.axis_unit)
            return pos

    def check_position(self):
        """Get the current position checking the hardware position (deprecated)"""
        deprecation_msg("check_position is deprecated, use get_actuator_value")
        pos = self.hardware.get_actuator_value()
        return pos

    def _initialize_hardware(self, params_state=None, controller: Optional[HardwareController] = None) -> edict:
        """Initialize an actuator plugin and connect signals.

        Parameters
        ----------
        params_state : dict
            Saved parameter state to restore
        controller : object, optional
            Shared controller instance

        Returns
        -------
        edict
            Status dictionary with 'initialized', 'info', 'controller' keys
        """
        status = edict(initialized=False, info="")
        try:
            class_, params = self._get_plugin_class_and_params(self.actuator)
            self.hardware:DAQ_Move_base = class_(self, params_state)
            assert self.hardware is not None

            try:
                infos = self.hardware.ini_stage(controller)
            except Exception as e:
                logger.exception("Hardware couldn't be initialized", exc_info=e)
                infos = str(e), False

            if isinstance(infos, edict):  # following old plugin templating
                status.update(infos)
                deprecation_msg(
                    "Returns from init_stage should now be a string and a boolean,"
                    " see pymodaq_plugins_template",
                    stacklevel=3,
                )
            else:
                status.info = infos[0]
                status.initialized = infos[1]

            status.controller = self.hardware.controller
            self.controller = self.hardware.controller  # Update base class controller
            self.hardware.move_done_signal.connect(self.move_done)

            if status.initialized:
                self.status_sig.emit(
                    ThreadCommand(
                        ThreadStatusMove.GET_ACTUATOR_VALUE, self.get_actuator_value()
                    )
                )

            return status
        except Exception as e:
            self.logger.exception(str(e))
            return status

    def move_abs(self, position: DataActuator, polling: bool = True) -> None:
        """

        """
        assert self.hardware is not None
        position = check_units(position, self.hardware.axis_unit)
        self.hardware.move_is_done = False
        self.hardware.ispolling = polling
        if self.hardware.data_actuator_type == self.hardware.data_actuator_type.float:
            self.hardware.move_abs(
                position.units_as(self.hardware.axis_unit).value()
            )  # convert to plugin controller current axis units
        else:
            position.units = (
                self.hardware.axis_unit
            )  # convert to plugin controller current axis units
            self.hardware.move_abs(position)
        self.hardware.poll_moving()

    def move_rel(self, rel_position: DataActuator, polling: bool = True) -> None:
        """

        """
        assert self.hardware is not None
        rel_position = check_units(rel_position, self.hardware.axis_unit)
        self.hardware.move_is_done = False
        self.hardware.ispolling = polling

        if self.hardware.data_actuator_type.name == 'float':
            self.hardware.move_rel(rel_position.units_as(self.hardware.axis_unit).value())
        else:
            rel_position.units = (
                self.hardware.axis_unit
            )  # convert to plugin current axis units
            self.hardware.move_rel(rel_position)

        self.hardware.poll_moving()

    @Slot(float)
    def Move_Stoped(self, pos):
        """
        Send a "move_done" Thread Command with the given position as an attribute.

        See Also
        --------
        DAQ_utils.ThreadCommand
        """
        self.status_sig.emit(ThreadCommand(ThreadStatusMove.MOVE_DONE, pos))

    def move_home(self):
        """
        Make the hardware move to the init position.

        """
        assert self.hardware is not None
        self.hardware.move_is_done = False
        self.hardware.move_home()

    @Slot(DataActuator)
    def move_done(self, pos: DataActuator):
        """Send the move_done signal back to the main class"""
        self._current_value = pos
        self.status_sig.emit(
            ThreadCommand(command=ThreadStatusMove.MOVE_DONE, attribute=pos)
        )

    def _handle_specific_command(self, command: ThreadCommand):
        """Handle actuator-specific commands.

        Supported commands:
            * MOVE_ABS: Move to absolute position
            * MOVE_REL: Move relative to current position
            * MOVE_HOME: Move to home position
            * GET_ACTUATOR_VALUE: Get current actuator value
            * STOP_MOTION: Stop any ongoing motion
            * RESET_STOP_MOTION: Reset the motion stopped flag
            * custom: Any command supported by the hardware plugin

        Parameters
        ----------
        command : ThreadCommand
            The specific command to pass to the actuator hardware
        """
        cmd = command.command

        if cmd == ControlToHardwareMove.MOVE_ABS:
            self.move_abs(*command.attribute)

        elif cmd == ControlToHardwareMove.MOVE_REL:
            self.move_rel(*command.attribute)

        elif cmd == ControlToHardwareMove.MOVE_HOME:
            self.move_home()

        elif cmd == ControlToHardwareMove.GET_ACTUATOR_VALUE:
            pos = self.get_actuator_value()
            self.status_sig.emit(
                ThreadCommand(ThreadStatusMove.GET_ACTUATOR_VALUE, pos)
            )

        elif cmd == ControlToHardwareMove.STOP_MOTION:
            self.stop_motion()

        elif cmd == ControlToHardwareMove.RESET_STOP_MOTION:
            self.motion_stoped = False

        else:  # Custom commands for particular plugins
            if hasattr(self.hardware, cmd):
                method = getattr(self.hardware, cmd)
                if isinstance(command.attribute, list):
                    method(*command.attribute)
                elif isinstance(command.attribute, dict):
                    method(**command.attribute)

    def stop_motion(self):
        """
        stop hardware motion with motion_stopped attribute updtaed to True and a status signal sended with an "update_status" Thread Command

        See Also
        --------
        DAQ_utils.ThreadCommand, stop_motion
        """
        self.status_sig.emit(
            ThreadCommand(command="Update_Status", attribute=["Motion stoping", "log"])
        )
        self.motion_stoped = True
        assert self.hardware is not None
        if self.hardware is not None and self.hardware.controller is not None:
            self.hardware.stop_motion()
        self.hardware.poll_timer.stop()



def main(init_qt=True):
    from pymodaq.utils.gui_utils.loader_utils import create_load_daq_move
    app = mkQApp("PyMoDAQ Move")
    shared_ui, daq_move = create_load_daq_move('simple')
    shared_ui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
