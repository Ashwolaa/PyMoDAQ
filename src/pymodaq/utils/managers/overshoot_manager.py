from qtpy import QtWidgets
import sys

from pymodaq_gui.parameter import ioxml, Parameter
from pymodaq_gui.parameter.pymodaq_ptypes import registerParameterType, GroupParameter
from pymodaq_gui.managers.config_manager import ConfigManager

# check if overshoot_configurations directory exists on the drive
from pymodaq.utils.config import get_set_overshoot_path

overshoot_path = get_set_overshoot_path()


class PresetScalableGroupMove(GroupParameter):
    """
        |

        ================ =============
        **Attributes**    **Type**
        *opts*            dictionnary
        ================ =============

        See Also
        --------
        hardware.DAQ_Move_Stage_type
    """

    def __init__(self, **opts):
        opts['type'] = 'groupmoveover'
        opts['addText'] = "Add"
        opts['addList'] = opts['movelist']
        super().__init__(**opts)

    def addNew(self, name):
        """
            Add a child.

            =============== ===========
            **Parameters**   **Type**
            *typ*            string
            =============== ===========
        """
        name_prefix = 'move'
        child_indexes = [int(par.name()[len(name_prefix) + 1:]) for par in self.children()]
        if not child_indexes:
            newindex = 0
        else:
            newindex = max(child_indexes) + 1

        child = {'title': name, 'name': f'{name_prefix}{newindex:02.0f}', 'type': 'group', 'removable': True,
                 'children': [
                     {'title': 'Move if overshoot?:', 'name': 'move_overshoot', 'type': 'bool', 'value': True},
                     {'title': 'Position:', 'name': 'position', 'type': 'float', 'value': 0}], 'removable': True,
                 'renamable': False}

        self.addChild(child)


registerParameterType('groupmoveover', PresetScalableGroupMove, override=True)


class PresetScalableGroupDet(GroupParameter):
    """
        =============== ==============
        **Attributes**    **Type**
        *opts*            dictionnary
        *options*         string list
        =============== ==============

        See Also
        --------
    """

    def __init__(self, **opts):
        opts['type'] = 'groupdetover'
        opts['addText'] = "Add"
        opts['addList'] = opts['detlist']
        opts['movelist'] = opts['movelist']

        super().__init__(**opts)

    def addNew(self, name):
        """
            Add a child.

            =============== ===========  ================
            **Parameters**    **Type**   **Description*
            *typ*             string     the viewer name
            =============== ===========  ================
        """
        try:
            name_prefix = 'det'
            child_indexes = [int(par.name()[len(name_prefix) + 1:]) for par in self.children()]
            if not child_indexes:
                newindex = 0
            else:
                newindex = max(child_indexes) + 1

            child = {'title': name, 'name': f'{name_prefix}{newindex:02.0f}', 'type': 'group', 'children': [
                {'title': 'Trig overshoot?:', 'name': 'trig_overshoot', 'type': 'bool', 'value': True},
                {'title': 'Overshoot value:', 'name': 'overshoot_value', 'type': 'float', 'value': 20},
                {'title': 'Triggered Moves:', 'name': 'params', 'type': 'groupmoveover',
                 'movelist': self.opts['movelist']}], 'removable': True, 'renamable': False}

            self.addChild(child)
        except Exception as e:
            print(str(e))


registerParameterType('groupdetover', PresetScalableGroupDet, override=True)


class OvershootManager(ConfigManager):
    title = "Overshoot"
    name = "overshoot"

    def __init__(self, msgbox=False, det_modules=[], actuators_modules=[]):
        self.overshoot_params = None
        self.det_modules = det_modules
        self.actuators_modules = actuators_modules
        self._activated = False   
        #Init comes after as the msgbox is created at the ConfigManager level     
        super().__init__(config_path=overshoot_path, msgbox=msgbox)

    @property
    def activated(self) -> bool:
        return self._activated

    @activated.setter
    def activated(self, status: bool):
        self._activated = status

    def make_config(self):
        params_det = [
            {
                "title": "Detectors:",
                "name": "Detectors",
                "type": "groupdetover",
                "detlist": self.det_modules,
                "movelist": self.actuators_modules,
            }
        ]
        return params_det

    def activate_overshoot(self, det_modules, act_modules, status: bool):
        det_titles = [det.title for det in det_modules]
        move_titles = [move.title for move in act_modules]

        if self.overshoot_params is not None:
            for det_param in self.overshoot_params.child(
                    'Detectors').children():
                if det_param['trig_overshoot']:
                    det_index = det_titles.index(det_param.opts['title'])
                    det_module = det_modules[det_index]
                    det_module.settings.child(
                        'main_settings', 'overshoot', 'stop_overshoot').setValue(status)
                    det_module.settings.child(
                        'main_settings', 'overshoot', 'overshoot_value').setValue(
                        det_param['overshoot_value'])
                    for move_param in det_param.child('params').children():
                        if move_param['move_overshoot']:
                            move_index = move_titles.index(move_param.opts['title'])
                            move_module = act_modules[move_index]
                            if status:
                                det_module.overshoot_signal.connect(
                                    self.create_overshoot_fun(
                                        move_module, move_param['position']))
                            else:
                                try:
                                    det_module.overshoot_signal.disconnect()
                                except Exception as e:
                                    pass

    @staticmethod
    def create_overshoot_fun(move_module, position):
        return lambda: move_module.move_abs(position)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    prog = OvershootManager(True, ['det camera', 'det current'], ['Move X', 'Move Y'])

    sys.exit(app.exec_())
