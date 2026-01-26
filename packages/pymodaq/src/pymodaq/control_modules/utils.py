# -*- coding: utf-8 -*-
"""
Created the 03/10/2022

@author: Sebastien Weber
"""
from abc import abstractmethod
from random import randint
from typing import Optional, Type, Union
from easydict import EasyDict as edict

from qtpy.QtCore import Signal, QObject, Qt, Slot, QThread

from pymodaq_utils.utils import ThreadCommand
from pymodaq_utils.config import Config
from pymodaq_utils.logger import get_base_logger, set_logger, get_module_name
from pymodaq_utils.enums import StrEnum

from pymodaq_gui.parameter import Parameter, ioxml
from pymodaq_gui.parameter.utils import ParameterWithPath
from pymodaq_gui.parameter import utils as putils
from pymodaq_gui.parameter.ioxml import VALID_FOR_CONFIGURATION
from pymodaq_gui.managers.parameter_manager import ParameterManager
from pymodaq_gui.h5modules.saving import H5Saver

from pymodaq.utils.tcp_ip.tcp_server_client import TCPClient
from pymodaq.utils.leco.pymodaq_listener import ActorListener, LECOClientCommands, LECOCommands
from pymodaq.utils.h5modules.module_saving import DetectorSaver, ActuatorSaver
from pymodaq.utils.config import Config as ControlModulesConfig

from pymodaq.control_modules.thread_commands import ThreadStatus


class ControleModuleType(StrEnum):
    DAQ_MOVE = 'DAQ_Move'
    DAQ_VIEWER = 'DAQ_Viewer'


class ControllerStatus(StrEnum):
    MASTER = 'Master'
    SLAVE = 'Slave'





def create_controller_param(axis_name: str = None, axis_names: Optional[list[str]] = None) -> dict:
    controller_param = {'title': 'Controller:', 'name': 'controller', 'type': 'group', 'children': [
        {'title': 'Controller Status:', 'name': 'controller_status', 'type': 'list',
         'value': ControllerStatus.MASTER.value,
         'limits': [ControllerStatus.MASTER.value, ControllerStatus.SLAVE.value]},
        {'title': 'Controller ID:', 'name': 'controller_ID', 'type': 'int', 'value': randint(0, 9999),
         'default': 0, 'readonly': False},

    ]}
    if axis_names is not None and axis_name is not None:
        controller_param['children'].append({'title': 'Axis:', 'name': 'axis', 'type': 'list',
                                             'limits': axis_names.copy(),
                                             'value': axis_name,
                                             VALID_FOR_CONFIGURATION: False})
    return controller_param


def create_remote_connection_params() -> list[dict]:
    """Create common remote connection parameter definitions (TCP/IP and LECO)

    These parameters are shared between DAQ_Move and DAQ_Viewer control modules
    and provide the settings for connecting to remote TCP/IP servers or LECO instances.

    Returns
    -------
    list of dict
        Parameter definitions for TCP/IP and LECO remote connections
    """
    return [
        {'title': 'TCP/IP options:', 'name': 'tcpip', 'type': 'group', 'visible': True,
         'expanded': False, 'children': [
            {'title': 'Connect to server:', 'name': 'connect_server', 'type': 'bool_push',
             'label': 'Connect', 'value': False},
            {'title': 'Connected?:', 'name': 'tcp_connected', 'type': 'led', 'value': False,
             VALID_FOR_CONFIGURATION: False, 'readonly': True},
            {'title': 'IP address:', 'name': 'ip_address', 'type': 'str',
             'value': config_utils('network', 'tcp-server', 'ip')},
            {'title': 'Port:', 'name': 'port', 'type': 'int',
             'value': config_utils('network', 'tcp-server', 'port')},
        ]},
        {'title': 'LECO options:', 'name': 'leco', 'type': 'group', 'visible': True,
         'expanded': False, 'children': [
            {'title': 'Connect:', 'name': 'connect_leco_server', 'type': 'bool_push',
             'label': 'Connect', 'value': False},
            {'title': 'Connected?:', 'name': 'leco_connected', 'type': 'led', 'value': False,
             VALID_FOR_CONFIGURATION: False, 'readonly': True},
            {'title': 'Name', 'name': 'leco_name', 'type': 'str', 'value': "", 'default': ""},
            {'title': 'Host:', 'name': 'host', 'type': 'str',
             'value': config_utils('network', "leco-server", "host"), "default": "localhost"},
            {'title': 'Port:', 'name': 'port', 'type': 'int',
             'value': config_utils('network', 'leco-server', 'port')},
        ]},
    ]


config_utils = Config()
config = ControlModulesConfig()
logger = set_logger(get_module_name(__file__))


class ControlModule(QObject):
    """Abstract Base class common to both DAQ_Move and DAQ_Viewer control modules

    Attributes
    ----------
    init_signal : Signal[bool]
        This signal is emitted when the chosen hardware is correctly initialized
    command_hardware : Signal[ThreadCommand]
        This signal is used to communicate with the instrument plugin within a separate thread
    command_tcpip : Signal[ThreadCommand]
        This signal is used to communicate through the TCP/IP Network
    quit_signal : Signal[]
        This signal is emitted when the user requested to stop the module
    """
    init_signal = Signal(bool)
    command_hardware = Signal(ThreadCommand)
    _command_tcpip = Signal(ThreadCommand)
    quit_signal = Signal()
    _update_settings_signal = Signal(edict)
    status_sig = Signal(str)
    custom_sig = Signal(ThreadCommand)
    ui = None

    def __init__(self):
        super().__init__()
        self._title = ""
        self.config = config
        # the hardware controller instance set after initialization and to be used by other modules if they share the
        # same controller
        self.controller = None
        self._initialized_state = False
        self._send_to_tcpip = False
        self._tcpclient_thread = None
        self._hardware_thread = None

        self.plugin_config: Optional[Config] = None

        self._h5saver: Optional[H5Saver] = None
        self._module_and_data_saver = None

    def __repr__(self):
        return f'{self.__class__.__name__}: {self.title}'

    def create_new_file(self, new_file: bool):
        if new_file:
            self.close_file()

        self.module_and_data_saver.h5saver = self.h5saver
        return True

    @property
    def h5saver(self):
        if self._h5saver is None:
            self._h5saver = H5Saver(backend=config_utils('general', 'hdf5_backend'))
        if self._h5saver.h5_file is None:
            self._h5saver.init_file(update_h5=True)
        if not self._h5saver.isopen():
            self._h5saver.init_file(addhoc_file_path=self._h5saver.settings['current_h5_file'])
        return self._h5saver

    @h5saver.setter
    def h5saver(self, h5saver_temp: H5Saver):
        self._h5saver = h5saver_temp

    def close_file(self):
        self.h5saver.close_file()

    @property
    def module_and_data_saver(self):
        if self._module_and_data_saver.h5saver is None or not self._module_and_data_saver.h5saver.isopen():
            self._module_and_data_saver.h5saver = self.h5saver
        return self._module_and_data_saver

    @module_and_data_saver.setter
    def module_and_data_saver(self, mod: Union[DetectorSaver, ActuatorSaver]):
        self._module_and_data_saver = mod
        self._module_and_data_saver.h5saver = self.h5saver

    def custom_command(self, command: str, **kwargs):
        self.command_hardware.emit(ThreadCommand(command, kwargs))

    def thread_status(self, status: ThreadCommand, control_module_type='detector'):
        """Get back info (using the ThreadCommand object) from the hardware

        And re-emit this ThreadCommand using the custom_sig signal if it should be used in a higher level module


        Parameters
        ----------
        status: ThreadCommand
            The info returned from the hardware, the command (str) can be either:
                * Update_Status: display messages and log info (deprecated)
                * update_status: display info on the UI status bar
                * close: close the current thread and delete corresponding attribute on cascade.
                * update_settings: Update the "detector setting" node in the settings tree.
                * update_main_settings: update the "main setting" node in the settings tree
                * raise_timeout:
                * show_splash: Display the splash screen with attribute as message
                * close_splash
                * show_config: display the plugin configuration
        """

        if status.command == "Update_Status":
            # legacy
            if len(status.attribute) > 1:
                self.update_status(status.attribute[0], log=status.attribute[1])
            else:
                self.update_status(status.attribute[0])

        elif status.command == ThreadStatus.UPDATE_STATUS:
            self.update_status(status.attribute)

        elif status.command == ThreadStatus.CLOSE:
            try:
                self.update_status(status.attribute[0])
                self._hardware_thread.quit()
                terminated = self._hardware_thread.wait(5000)
                if not terminated:
                    self._hardware_thread.terminate()
                    self._hardware_thread.wait()
                    self.update_status('thread is locked?!', 'log')
            except Exception as e:
                logger.exception(f'Wrong call to the "close" command: \n{str(e)}')

            self._initialized_state = False
            self.init_signal.emit(self._initialized_state)

        elif status.command == ThreadStatus.UPDATE_MAIN_SETTINGS:
            # this is a way for the plugins to update main settings of the ui (solely values, limits and options)
            try:
                if status.attribute[2] == 'value':
                    self.settings.child('main_settings', *status.attribute[0]).setValue(status.attribute[1])
                elif status.attribute[2] == 'limits':
                    self.settings.child('main_settings', *status.attribute[0]).setLimits(status.attribute[1])
                elif status.attribute[2] == 'options':
                    self.settings.child('main_settings', *status.attribute[0]).setOpts(**status.attribute[1])
            except Exception as e:
                logger.exception(f'Wrong call to the "update_main_settings" command: \n{str(e)}')

        elif status.command == ThreadStatus.UPDATE_SETTINGS:
            # using this the settings shown in the UI for the plugin reflects the real plugin settings
            try:
                self.settings.sigTreeStateChanged.disconnect(
                    self.parameter_tree_changed)  # any changes on the detcetor settings will update accordingly the gui
            except Exception as e:
                logger.exception(str(e))
            try:
                if status.attribute[2] == 'value':
                    self.settings.child(f'{control_module_type}_settings',
                                        *status.attribute[0]).setValue(status.attribute[1])
                elif status.attribute[2] == 'limits':
                    self.settings.child(f'{control_module_type}_settings',
                                        *status.attribute[0]).setLimits(status.attribute[1])

                elif status.attribute[2] == 'options':
                    self.settings.child(f'{control_module_type}_settings',
                                        *status.attribute[0]).setOpts(**status.attribute[1])
                elif status.attribute[2] == 'childAdded':
                    child = Parameter.create(name='tmp')
                    child.restoreState(status.attribute[1][0])
                    self.settings.child(f'{control_module_type}_settings',
                                        *status.attribute[0]).addChild(status.attribute[1][0])

            except Exception as e:
                logger.exception(f'Wrong call to the "update_settings" command: \n{str(e)}')
            self.settings.sigTreeStateChanged.connect(self.parameter_tree_changed)

        elif status.command == ThreadStatus.UPDATE_UI:
            try:
                if self.ui is not None:
                    if hasattr(self.ui, status.attribute):
                        getattr(self.ui, status.attribute)(*status.args,
                                                           **status.kwargs)
            except Exception as e:
                logger.info(f'Wrong call to the "update_ui" command: \n{str(e)}')

        elif status.command == ThreadStatus.RAISE_TIMEOUT:
            self.raise_timeout()

        elif status.command == ThreadStatus.SHOW_SPLASH:
            self.settings_tree.setEnabled(False)
            self.splash_sc.show()
            self.splash_sc.raise_()
            self.splash_sc.showMessage(status.attribute, color=Qt.white)

        elif status.command == ThreadStatus.CLOSE_SPLASH:
            self.splash_sc.close()
            self.settings_tree.setEnabled(True)

        self.custom_sig.emit(status)  # to be used if needed in custom application connected to this module

    @property
    def module_type(self) -> ControleModuleType:
        """Get the module type, either DAQ_Move or DAQ_viewer"""
        return ControleModuleType(type(self).__name__)

    @property
    def initialized_state(self):
        """bool: Check if the module is initialized"""
        return self._initialized_state

    @property
    def title(self):
        """str: get the title of the module"""
        return self._title

    def grab(self):
        """Programmatic entry to grab data from detectors or current value from actuator"""
        raise NotImplementedError

    def stop_grab(self):
        """Programmatic entry to stop data grabbing from detectors or current value polling from actuator"""
        raise NotImplementedError

    def _add_data_to_saver(self, *args, **kwargs):
        raise NotImplementedError

    def append_data(self, *args, **kwargs):
        raise NotImplementedError

    def insert_data(self, *args, **kwargs):
        raise NotImplementedError

    def quit_fun(self):
        """Programmatic entry to quit the control module"""
        raise NotImplementedError

    def init_hardware(self, do_init=True):
        """Programmatic entry to initialize/deinitialize the control module

        Parameters
        ----------
        do_init : bool
            if True initialize the selected hardware else deinitialize it

        See Also
        --------
        :meth:`init_hardware_ui`
        """
        raise NotImplementedError

    def init_hardware_ui(self, do_init=True):
        """Programmatic entry to simulate a click on the user interface init button

        Parameters
        ----------
        do_init : bool
            if True initialize the selected hardware else deinitialize it

        Notes
        -----
        This method should be preferred to :meth:`init_hardware`
        """
        if self.ui is not None:
            self.ui.do_init(do_init)

    def show_config(self, config: Config) -> Config:
        """ Display in a tree the current configuration"""
        if config is not None:
            from pymodaq_gui.utils.widgets.tree_toml import TreeFromToml
            config_tree = TreeFromToml(config)
            config_tree.show_dialog()

            return ControlModulesConfig()

    def update_status(self, txt: str, log=True):
        """Display a message in the ui status bar and eventually log the message

        Parameters
        ----------
        txt : str
            message to display
        log : bool
            if True, log the message in the logger
        """
        if self.ui is not None:
            self.ui.display_status(txt)
        self.status_sig.emit(txt)
        if log:
            logger.info(txt)

    def manage_ui_actions(self, action_name: str, attribute: str, value):
        """Method to manage actions for the UI (if any).

        Will try to apply the given value to the given attribute of the corresponding action

        Parameters
        ----------
        action_name: str
        attribute: method signature or attribute
        value: object
            actual type and value depend on the triggered attribute

        Examples
        --------
        >>>manage_ui_actions('quit', 'setEnabled', False)
        # will disable the quit action (button) on the UI
        """
        if self.ui is not None:
            if self.ui.has_action(action_name):
                action = self.ui.get_action(action_name)
                if hasattr(action, attribute):
                    attr = getattr(action, attribute)
                    if callable(attr):
                        attr(value)
                    else:
                        attr = value


class ParameterControlModule(ParameterManager, ControlModule):
    """Base class for a control module with parameters."""

    _update_settings_signal = Signal(edict)

    listener_class: Type[ActorListener] = ActorListener

    def __init__(self, **kwargs):
        action_list = kwargs.get("action_list", ("search", "save", "update"))
        ParameterManager.__init__(self, action_list=action_list)
        ControlModule.__init__(self)

    @property
    @abstractmethod
    def _plugin_settings_name(self) -> str:
        """Return the name of the plugin settings parameter group.

        Returns
        -------
        str
            'move_settings' for DAQ_Move or 'detector_settings' for DAQ_Viewer
        """

    @property
    @abstractmethod
    def _saver_class(self) -> Type:
        """Return the saver class to use for this control module.

        Returns
        -------
        Type
            ActuatorTimeSaver for DAQ_Move or DetectorSaver for DAQ_Viewer
        """

    def quit_fun(self):
        """Programmatic quitting of the control module.

        De-initializes the hardware if initialized, emits quit_signal,
        calls _cleanup_resources() for subclass-specific cleanup,
        and closes the UI if present.
        """
        if self._initialized_state:
            self.init_hardware(False)
        self.quit_signal.emit()
        self._cleanup_resources()
        if self.ui is not None:
            try:
                self.ui.close()
            except Exception as e:
                logger.exception(str(e))

    def _cleanup_resources(self):
        """Override in subclasses for specific cleanup.

        Called during quit_fun() before closing the UI.
        """
        pass

    def child_added(self, param, data):
        """Apply addition of settings to the hardware.

        Parameters
        ----------
        param: Parameter
            The parent parameter where the child was added
        data: tuple
            Tuple containing the added child parameter
        """
        path = self.settings.childPath(param)
        if path is not None and 'main_settings' not in path:
            self._update_settings_signal.emit(
                edict(path=path, param=data[0].saveState(), change='childAdded'))

    def param_deleted(self, param):
        """Apply deletion of settings to the hardware.

        Parameters
        ----------
        param: Parameter
            The parameter that was deleted
        """
        if param.name() not in putils.iter_children(self.settings.child('main_settings'), []):
            self._update_settings_signal.emit(
                edict(path=[self._plugin_settings_name], param=param, change='parent'))

    def apply_controller_parameters(self, controller_param: Parameter):
        """Apply controller parameters (Master/Slave, ID, eventually axes) to the ControlModule instance

        Parameters
        ----------
        controller_param: Parameter
            Parameter object containing the controller parameters
        """
        try:
            if self.module_type == ControleModuleType.DAQ_VIEWER:
                controller_settings = self.settings.child('detector_settings', 'controller')
            elif self.module_type == ControleModuleType.DAQ_MOVE:
                controller_settings = self.settings.child('move_settings', 'controller')
            else:
                raise TypeError('Unknown ControlModuleType')
            controller_settings.restoreState(controller_param.saveState())

        except Exception as e:
            logger.exception(f'Error applying controller parameters: {str(e)}')

    def value_changed(self, param: Parameter) -> Optional[Parameter]:
        """ParameterManager subclassed method. Process events from value changed by user in the UI Settings

        Parameters
        ----------
        param: Parameter
            a given parameter whose value has been changed by user

        Returns
        -------
        Optional[Parameter]
            None if the parameter was handled, otherwise the parameter for subclass handling
        """
        if param.name() == 'plugin_config':
            self.show_config(self.plugin_config)

        elif param.name() == 'connect_server':
            if param.value():
                self.connect_tcp_ip()
            else:
                self._command_tcpip.emit(ThreadCommand('quit', ))

        elif param.name() == 'ip_address' or param.name == 'port':
            self._command_tcpip.emit(
                ThreadCommand('update_connection',
                              dict(ipaddress=self.settings['main_settings', 'tcpip', 'ip_address'],
                                   port=self.settings['main_settings', 'tcpip', 'port'])))

        elif param.name() == 'connect_leco_server':
            self.connect_leco(param.value())

        elif param.name() == "name":
            name = param.value()
            try:
                self._leco_client.name = name
            except AttributeError:
                pass

        elif param.name() == 'continuous_saving_opt':
            self.settings.child('saver_settings').setOpts(visible=param.value())
            return None  # Handled

        elif param.name() in putils.iter_children(self.settings.child('saver_settings'), []):
            path = self.settings.childPath(param)
            if param.name() == 'do_save':
                self.setup_continuous_saving(param.value())
            self._get_h5saver_for_saving().settings.child(*path[1:]).setValue(param.value())
            return None  # Handled

        else:
            # not handled
            return param

    def _get_h5saver_for_saving(self) -> H5Saver:
        """Return the H5Saver instance to use for continuous saving.

        Override in subclasses if a different h5saver is used.

        Returns
        -------
        H5Saver
            The H5Saver instance for continuous saving
        """
        return self.h5saver

    def setup_continuous_saving(self, init: bool = True):
        """Configure the objects dealing with the continuous saving mode.

        Parameters
        ----------
        init: bool
            If True, initialize continuous saving. If False, close the file.
        """
        if init:
            self._setup_continuous_saving_init()
        else:
            self._get_h5saver_for_saving().close_file()

    def _setup_continuous_saving_init(self):
        """Initialize continuous saving - called by setup_continuous_saving.

        Override in subclasses for custom initialization.
        """
        self.module_and_data_saver = self._saver_class(self)
        h5saver = self._get_h5saver_for_saving()
        self.module_and_data_saver.h5saver = h5saver
        h5saver.settings.child('do_save').sigValueChanged.connect(self._init_continuous_save)

    @abstractmethod
    def _init_continuous_save(self):
        """Initialize continuous save - module-specific implementation.

        Called when do_save setting changes.
        """

    def init_hardware(self, do_init=True):
        """Template method for hardware initialization.

        Parameters
        ----------
        do_init: bool
            If True, initialize the hardware. If False, deinitialize.
        """
        if not do_init:
            self._deinit_hardware()
        else:
            self._do_init_hardware()

    def _deinit_hardware(self):
        """Common de-initialization."""
        try:
            self.command_hardware.emit(ThreadCommand(self._close_command))
            if self.ui is not None:
                self._set_ui_init_state(False)
        except Exception as e:
            logger.exception(str(e))

    def _do_init_hardware(self):
        """Common initialization - connects signals, starts thread."""
        try:
            hardware = self._create_hardware_instance()
            self._hardware_thread = QThread()
            if self._run_hardware_in_thread:
                hardware.moveToThread(self._hardware_thread)

            self._connect_hardware_signals(hardware)

            self._hardware_thread.hardware = hardware
            if self._run_hardware_in_thread:
                self._hardware_thread.start()
            self._emit_init_command()
            self._post_init_hardware()
        except Exception as e:
            logger.exception(str(e))

    def _connect_hardware_signals(self, hardware):
        """Connect common signals - extend in subclasses for additional signals."""
        self.command_hardware[ThreadCommand].connect(hardware.queue_command)
        hardware.status_sig[ThreadCommand].connect(self.thread_status)
        self._update_settings_signal[edict].connect(hardware.update_settings)

    def _post_init_hardware(self):
        """Hook for post-initialization actions - override in subclasses."""
        pass

    @property
    @abstractmethod
    def _close_command(self) -> str:
        """Return the close command enum value."""

    @property
    def _run_hardware_in_thread(self) -> bool:
        """Whether to run hardware in separate thread (default True)."""
        return True

    @abstractmethod
    def _create_hardware_instance(self):
        """Factory method - create hardware instance."""

    @abstractmethod
    def _emit_init_command(self):
        """Emit initialization command to hardware."""

    @abstractmethod
    def _set_ui_init_state(self, status: bool):
        """Set UI initialization state."""

    def _update_settings(self, param: Parameter):
        # I do not understand what it does
        path = self.settings.childPath(param)
        if path is not None:
            if 'main_settings' not in path:
                self._update_settings_signal.emit(edict(path=path, param=param, change='value'))
                if self.settings.child('main_settings', 'tcpip', 'tcp_connected').value():
                    self._command_tcpip.emit(ThreadCommand('send_info', dict(path=path, param=param)))
                if self.settings.child('main_settings', 'leco', 'leco_connected').value():
                    self._command_tcpip.emit(
                        ThreadCommand(LECOCommands.SEND_INFO,
                                      ParameterWithPath(param, path)))

    def connect_tcp_ip(self, params_state=None, client_type: str = "GRABBER") -> None:
        """Init a TCPClient in a separated thread to communicate with a distant TCp/IP Server

        Use the settings: ip_address and port to specify the connection

        See Also
        --------
        TCPServer
        """
        if self.settings.child('main_settings', 'tcpip', 'connect_server').value():
            self._tcpclient_thread = QThread()

            tcpclient = TCPClient(self.settings.child('main_settings', 'tcpip', 'ip_address').value(),
                                  self.settings.child('main_settings', 'tcpip', 'port').value(),
                                  params_state=params_state,
                                  client_type=client_type)
            tcpclient.moveToThread(self._tcpclient_thread)
            self._tcpclient_thread.tcpclient = tcpclient
            tcpclient.cmd_signal.connect(self.process_tcpip_cmds)

            self._command_tcpip[ThreadCommand].connect(tcpclient.queue_command)
            self._tcpclient_thread.started.connect(tcpclient.init_connection)

            self._tcpclient_thread.start()

    def get_leco_name(self) -> str:
        name = self.settings["main_settings", "leco", "leco_name"]
        if name == '':
            # take the module name as alternative
            name = self.settings["main_settings", "module_name"]
        if name == '':
            # a name is required, invent one
            name = f"viewer_{randint(0, 10000)}"
            name = self.settings.child("main_settings", "leco", "leco_name").setValue(name)
        return name

    def get_leco_host_port(self) -> tuple:
        host = self.settings["main_settings", "leco", "host"]
        port = self.settings["main_settings", "leco", "port"]
        if host == '':
            # take the localhost as default
            host = 'localhost'
        if port == '':
            # take the default port as 12300
            port = 12300
        return (host, port)    

    def connect_leco(self, connect: bool) -> None:
        if connect:
            name = self.get_leco_name()
            host, port = self.get_leco_host_port()
            try:
                self._leco_client.name = name
            except AttributeError:
                self._leco_client = self.listener_class(name=name, host=host, port=port)
                self._leco_client.cmd_signal.connect(self.process_tcpip_cmds)
            self._command_tcpip[ThreadCommand].connect(self._leco_client.queue_command)
            self._leco_client.start_listen()
            # self._leco_client.cmd_signal.emit(ThreadCommand(LECOCommands.SET_INFO, attribute=["detector_settings", ""]))
        else:
            self._command_tcpip.emit(ThreadCommand(LECOCommands.QUIT, ))
            try:
                self._command_tcpip[ThreadCommand].disconnect(self._leco_client.queue_command)
            except TypeError:
                pass  # already disconnected

    @Slot(ThreadCommand)
    def process_tcpip_cmds(self, status: ThreadCommand) -> Optional[ThreadCommand]:
        if status.command == 'connected':
            self.settings.child('main_settings', 'tcpip', 'tcp_connected').setValue(True)

        elif status.command == 'disconnected':
            self.settings.child('main_settings', 'tcpip', 'tcp_connected').setValue(False)

        elif status.command == LECOClientCommands.LECO_CONNECTED:
            self.settings.child('main_settings', 'leco', 'leco_connected').setValue(True)

        elif status.command == LECOClientCommands.LECO_DISCONNECTED:
            self.settings.child('main_settings', 'leco', 'leco_connected').setValue(False)

        elif status.command == 'Update_Status':
            self.thread_status(status)

        elif status.command == 'set_info':
            """ The Director sent a parameter to be updated"""
            path_in_settings = status.attribute.path
            if 'move' in self.__class__.__name__.lower():
                common_param = 'move_settings'
            else:
                common_param = 'detector_settings'
            if common_param in path_in_settings:
                param = self.settings.child(*path_in_settings)
            elif 'settings_client' in path_in_settings:
                param = self.settings.child(common_param, *path_in_settings[1:])
            else:
                param = self.settings.child(common_param, *path_in_settings)

            param.setValue(status.attribute.parameter.value())

        elif status.command == LECOCommands.GET_SETTINGS:
            """ The Director requested the content of the actuator settings"""
            if 'move' in self.__class__.__name__.lower():
                common_param = 'move_settings'
            else:
                common_param = 'detector_settings'
            self._command_tcpip.emit(
                ThreadCommand(LECOCommands.SET_DIRECTOR_SETTINGS,
                              ioxml.parameter_to_xml_string(
                                  self.settings.child(common_param))))

        else:
            # not handled
            return status


