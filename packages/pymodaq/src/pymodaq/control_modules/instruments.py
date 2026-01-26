from typing import Union
from importlib import import_module

from pymodaq_gui.parameter import Parameter

from pymodaq_gui.plotting.data_viewers import ViewersEnum
from pymodaq_utils.enums import BaseEnum

from pymodaq_utils.utils import find_dict_in_list_from_key_val, find_dicts_in_list_from_key_val
from pymodaq.utils.exceptions import DetectorError, ActuatorError
from pymodaq.control_modules.daq_viewer_ui.viewer_selector import SelectedDetector
from pymodaq.control_modules.daq_move_ui.actuator_selector import SelectedActuator

from pymodaq import CONTROL_MODULES


DET_TYPES = {'DAQ0D': find_dicts_in_list_from_key_val(CONTROL_MODULES, 'type', 'daq_0Dviewer'),
             'DAQ1D': find_dicts_in_list_from_key_val(CONTROL_MODULES, 'type', 'daq_1Dviewer'),
             'DAQ2D': find_dicts_in_list_from_key_val(CONTROL_MODULES, 'type', 'daq_2Dviewer'),
             'DAQND': find_dicts_in_list_from_key_val(CONTROL_MODULES, 'type', 'daq_NDviewer'),
             }
if len(DET_TYPES['DAQ0D']) == 0:
    raise DetectorError('No installed Detector')

ACTUATOR_TYPES = find_dicts_in_list_from_key_val(CONTROL_MODULES, 'type', 'daq_move')
ACTUATOR_NAMES = [mov["name"] for mov in ACTUATOR_TYPES]
if len(ACTUATOR_TYPES) == 0:
    raise ActuatorError("No installed Actuator")



class DAQTypesEnum(BaseEnum):
    """enum relating a given DAQType and a viewer type
    See Also
    --------
    pymodaq.utils.plotting.data_viewers.viewer.ViewersEnum
    """
    DAQ0D = 'Viewer0D'
    DAQ1D = 'Viewer1D'
    DAQ2D = 'Viewer2D'
    DAQND = 'ViewerND'

    def to_data_type(self):
        return ViewersEnum[self.value].value

    def to_viewer_type(self):
        return self.value

    def to_daq_type(self):
        return self.name

    def increase_dim(self, ndim: int):
        dim = self.get_dim()
        if dim != 'N':
            dim_as_int = int(dim) + ndim
            if dim_as_int > 2:
                dim = 'N'
            else:
                dim = str(dim_as_int)
        else:
            dim = 'N'
        return DAQTypesEnum(f'Viewer{dim}D')

    def get_dim(self):
        return self.value.split('Viewer')[1].split('D')[0]

def update_plugin_config(selected_module: Union[SelectedActuator,SelectedDetector]):
    if type(selected_module) is SelectedDetector:
        parent_module = get_detector_module(selected_module)
    elif type(selected_module) is SelectedActuator:
        parent_module = get_actuator_module(selected_module)
    else:
        raise ValueError("selected_module must be of type SelectedActuator or SelectedDetector")        
    mod = import_module(parent_module.__package__.split('.')[0])    
    return mod.config if hasattr(mod, 'config') else {}

def get_module(module_dict, name):
    return find_dict_in_list_from_key_val(module_dict, 'name', name)['module']

def get_detector_module(detector):
    return get_module(DET_TYPES[detector.daq_type.name], detector.module_name)

def get_actuator_module(actuator):
    return get_module(ACTUATOR_TYPES, actuator.module_name)

def get_plugin(module_dict, name, prefix, class_prefix, params_name):
    """
    Get the plugin class and its parameters from its name
    Parameters
    ----------
    module_dict : list of dict
        List of available plugins
    name : str
        Name of the plugin to get
    prefix : str
        Prefix used for the module import
    class_prefix : str
        Prefix used for the class name
    params_name : str
        Name of the parameters group
    Returns
    -------
    obj : class
        The plugin class
    params : Parameter
        The parameters of the plugin
    """    
    parent_module = get_module(module_dict, name)
    class_name = f"{class_prefix}{name}" 
    obj = getattr(getattr(parent_module, prefix + name), class_name)
    params = getattr(obj, 'params')
    params = Parameter.create(name=params_name, type='group', children=params)
    return obj, params

def get_detector_plugin(daq_type, det_name):
    """
    Get the detector plugin class and its parameters from its name
    Parameters
    ----------
    daq_type : str
        Type of the DAQ (e.g. 'DAQ0D', 'DAQ1D', etc.)
    det_name : str
        Name of the detector plugin
    Returns
    -------
    obj : class
        The viewer plugin class
    params : Parameter
        The parameters of the viewer plugin        
    """
    match_name = daq_type.lower()
    match_name = f'{match_name[0:3]}_{match_name[3:].upper()}viewer_'
    class_prefix = f"{match_name[0:7].upper()}{match_name[7:]}"
    return get_plugin(DET_TYPES[daq_type], det_name, match_name, class_prefix, 'Det Settings')

def get_actuator_plugin(act_name):
    """
    Get the actuator plugin class and its parameters from its name
    Parameters
    ----------
    act_name : str
        Name of the actuator plugin
    Returns
    -------
    obj : class
        The viewer plugin class
    params : Parameter
        The parameters of the viewer plugin        
    """    
    return get_plugin(ACTUATOR_TYPES, act_name, "daq_move_", "DAQ_Move_", "move_settings")
