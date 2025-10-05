import os
from pathlib import Path
import sys

from qtpy import QtWidgets
from qtpy.QtWidgets import QMessageBox, QDialogButtonBox, QDialog

import pymodaq_utils.config as config_mod
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq_gui.utils.file_io import select_file
from pymodaq_gui.parameter import ParameterTree, Parameter
from pymodaq_gui.parameter import ioxml
from pymodaq_gui.messenger import dialog as dialogbox
from pymodaq.utils import config as config_mod_pymodaq
from pymodaq.extensions import get_models
from pymodaq_gui.managers.config_manager import ConfigManager

import pymodaq.utils.managers.preset_manager_utils  # to register move and det types

logger = set_logger(get_module_name(__file__))

# check if preset_mode directory exists on the drive
preset_path = config_mod_pymodaq.get_set_preset_path()
overshoot_path = config_mod_pymodaq.get_set_overshoot_path()
layout_path = config_mod_pymodaq.get_set_layout_path()


class PresetManager(ConfigManager):
    name = 'preset'
    title = 'Preset'

    def __init__(self, msgbox=False, path=None, extra_params=[], param_options=[]):
        if path is None:
            path = preset_path
        else:
            assert isinstance(path, Path)

        self.extra_params = extra_params
        self.param_options = param_options
        # Init comes after as the msgbox is created at the ConfigManager level
        super().__init__(config_path=path, msgbox=msgbox)

    @property
    def filename(self) -> str:
        try:
            return self.settings["filename"]
        except:
            return None

    def make_config(self):
        params_move = [
            {"title": "Moves:", "name": "Moves", "type": "groupmove"}
        ]  # PresetScalableGroupMove(name="Moves")]
        params_det = [
            {"title": "Detectors:", "name": "Detectors", "type": "groupdet"}
        ]  # [PresetScalableGroupDet(name="Detectors")]

        return self.extra_params + params_move + params_det

    def set_new_config(self, file: str = None):
        super().set_new_config(file, show=False)
        try:
            for option in self.param_options:
                if "path" in option and "options_dict" in option:
                    self.settings.child(option["path"]).setOpts(
                        **option["options_dict"]
                    )
        except Exception as e:
            logger.exception(str(e))
        is_saved = self.show_config()
        return is_saved

    def parameter_tree_changed(self, param, changes):
        """
        Check for changes in the given (parameter,change,information) tuple list.
        In case of value changed, update the DAQscan_settings tree consequently.

        =============== ============================================ ==============================
        **Parameters**    **Type**                                     **Description**
        *param*           instance of pyqtgraph parameter              the parameter to be checked
        *changes*         (parameter,change,information) tuple list    the current changes state
        =============== ============================================ ==============================
        """
        for param, change, data in changes:
            path = self.settings.childPath(param)
            if change == "childAdded":
                if len(data) > 1:
                    if "params" in data[0].children():
                        data[0].child(
                            "params", "main_settings", "module_name"
                        ).setValue(data[0].child("name").value())

            elif change == "value":
                if param.name() == "name":
                    param.parent().child(
                        "params", "main_settings", "module_name"
                    ).setValue(param.value())

            elif change == "parent":
                pass

    def show_config(self):
        """ """
        is_saved = super().show_config()
        filename = self.settings.child("filename").value()       
        if is_saved:
            # check if overshoot configuration and layout configuration with same name exists => delete them if yes
            over_shoot_file = overshoot_path.joinpath(filename + ".xml")
            over_shoot_file.unlink(missing_ok=True)
            layout_file = layout_path.joinpath(filename + ".dock")
            layout_file.unlink(missing_ok=True)
        return is_saved


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    # prog = PresetManager(True)
    prog = PresetManager(True)

    sys.exit(app.exec_())
