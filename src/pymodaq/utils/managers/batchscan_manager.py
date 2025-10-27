from collections import OrderedDict
from pathlib import Path
import sys
from typing import List

from qtpy import QtWidgets, QtCore
from qtpy.QtWidgets import QMessageBox, QDialog, QDialogButtonBox

from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils import config as config_mod

from pymodaq_gui.managers.config_manager import ConfigManager
from pymodaq_gui.utils import Dock, file_io, DockArea
from pymodaq_gui.parameter import ioxml
from pymodaq_gui.messenger import messagebox

from pymodaq.utils.managers.modules_manager import ModulesManager
from pymodaq.utils.scanner import Scanner
from pymodaq.utils.scanner.scan_factory import ScannerBase
from pymodaq.utils.config import get_set_batch_path

logger = set_logger(get_module_name(__file__))

batch_path = get_set_batch_path()

params = [
    {'title': 'Actuators/Detectors Selection', 'name': 'modules', 'type': 'group', 'children': [
        {'title': 'detectors', 'name': 'detectors', 'type': 'itemselect'},
        {'title': 'Actuators', 'name': 'actuators', 'type': 'itemselect'},
    ]},
    ]


class BatchManager(ConfigManager):
    title = "Batch"
    name = "batch"

    def __init__(self, msgbox=False, actuators=[], detectors=[], path=None):
        if path is None:
            path = batch_path
        else:
            assert isinstance(path, Path)

        self.modules_manager: ModulesManager = ModulesManager(detectors, actuators)
        self.modules_manager.show_only_control_modules(True)
        self.modules_manager.actuators_changed[list].connect(self.update_actuators)
        self.modules_manager.settings_tree.setMinimumHeight(200)
        self.modules_manager.settings_tree.setMaximumHeight(200)

        self._scans = OrderedDict([])
        self.scanner = Scanner(actuators=self.modules_manager.actuators_all)
        self.scanner_widget = self.scanner.parent_widget

        # Init comes after as the msgbox is created at the ConfigManager level
        super().__init__(config_path=path, msgbox=msgbox)

        self.settings_tree.setMinimumWidth(400)
        self.settings_tree.setMaximumWidth(500)
        self.settings_tree.setMinimumHeight(500)

    def make_config(self):
        return [{'title': 'Scans', 'name': 'scans', 'type': 'group', 'children': []}]

    def validate_config(self):
        """Validate that actuators and detectors match the dashboard configuration"""
        children = self.settings.child('scans').children()
        if children:
            actuators = children[0].child('modules', 'actuators').value()['all_items']
            if actuators != self.modules_manager.actuators_name:
                messagebox(text='The loaded actuators from the batch file do not corresponds to the dashboard actuators')
                return False

            detectors = children[0].child('modules', 'detectors').value()['all_items']
            if detectors != self.modules_manager.detectors_name:
                messagebox(text='The loaded detectors from the batch file do not corresponds to the dashboard detectors')
                return False

        return True

    def get_act_dets(self):
        acts = dict([])
        dets = dict([])
        for name in [child.name() for child in self.settings.child('scans').children()]:
            acts[name] = self.settings.child('scans', name, 'modules', 'actuators').value()['selected']
            dets[name] = self.settings.child('scans', name, 'modules', 'detectors').value()['selected']
        return acts, dets

    def set_config_from_file(self, file_path: Path, show=True):
        """
        Load an existing batch configuration from an XML file.
        """
        if file_path is None or file_path is False:
            file_path = file_io.select_file(start_path=self.config_path, save=False, ext='xml')
            if file_path == '':
                return False

        # Use parent method to load and validate the settings
        if not super().set_config_from_file(file_path, show=False):
            return False

        if show:
            status = self.show_config(widget=self._create_batch_widget())
        else:
            self.settings_tree.setParameters(self.settings, showTop=False)
            status = True
        return status

    def set_file_batch(self, filename=None, show=True):
        """Backward compatibility wrapper - DEPRECATED, use set_config_from_file() instead"""
        logger.warning("set_file_batch() is deprecated, use set_config_from_file() instead")
        return self.set_config_from_file(filename, show)

    def set_scans(self):
        infos = []
        acts, dets = self.get_act_dets()
        self._scans = OrderedDict([])
        for name in [child.name() for child in self.settings.child('scans').children()]:
            self._scans[name] = Scanner(actuators=self.modules_manager.get_mods_from_names(acts[name], 'act'))
            self._scans[name].set_scan_from_settings(self.settings.child('scans', name, Scanner.settings_name),
                                                     self.settings.child('scans', name, ScannerBase.settings_name))
            infos.append(f'{name}: {acts[name]} / {dets[name]}')
            infos.append(f'{name}: {self._scans[name].get_scan_info()}')
        return infos

    def get_scan(self, name: str):
        """Get a Scanner object from name"""
        if len(self._scans) == 0:
            self.set_scans()
        return self._scans.get(name)

    @property
    def scans(self):
        return self._scans

    def get_scan_names(self) -> List[str]:
        return list(self._scans.keys())

    def set_new_config(self, file: str = None, show=True):
        """Create a new batch configuration"""
        super().set_new_config(file, show=False)
        if show:
            status = self.show_config(widget=self._create_batch_widget())
        else:
            status = True
        return status

    def set_new_batch(self):
        """Backward compatibility wrapper - DEPRECATED, use set_new_config() instead"""
        logger.warning("set_new_batch() is deprecated, use set_new_config() instead")
        return self.set_new_config()

    def _create_batch_widget(self):
        """Create the custom widget for batch configuration with modules manager and scanner"""
        widget = QtWidgets.QWidget()
        widget_layout = QtWidgets.QVBoxLayout()
        widget.setLayout(widget_layout)
        add_scan = QtWidgets.QPushButton('Add Scan')
        add_scan.clicked.connect(self.add_scan)
        widget_layout.addWidget(self.modules_manager.settings_tree)
        widget_layout.addWidget(self.scanner_widget)
        widget_layout.addWidget(add_scan)
        return widget

    def show_tree(self):
        """Backward compatibility wrapper - DEPRECATED, use show_config() instead"""
        logger.warning("show_tree() is deprecated, use show_config() instead")
        return self.show_config(widget=self._create_batch_widget())

    def set_scanner_settings(self, settings_tree: QtWidgets.QWidget):
        while True:
            child = self.scanner_widget.layout().takeAt(0)
            if not child:
                break
            child.widget().deleteLater()
            QtWidgets.QApplication.processEvents()

        self.scanner_widget.layout().addWidget(settings_tree)

    def update_actuators(self, actuators: List[str]):
        self.scanner.actuators = self.modules_manager.actuators

    def add_scan(self, name=None, title=None):
        if name is None or name is False:
            name_prefix = 'scan'
            child_indexes = [int(par.name()[len(name_prefix) + 1:]) for par in self.settings.child('scans').children()]
            if child_indexes == []:
                newindex = 0
            else:
                newindex = max(child_indexes) + 1
            name = f'{name_prefix}{newindex:02.0f}'
            title = f'Scan {newindex:02.0f}'

        child = {'title': title, 'name': name, 'type': 'group', 'removable': True, 'children': params}

        # self._scans[name] = Scanner(actuators=self.modules_manager.actuators)

        self.settings.child('scans').addChild(child)
        self.settings.child('scans', name, 'modules',
                            'actuators').setValue(dict(all_items=self.modules_manager.actuators_name,
                                                       selected=self.modules_manager.selected_actuators_name))
        self.settings.child('scans', name, 'modules',
                            'detectors').setValue(dict(all_items=self.modules_manager.detectors_name,
                                                       selected=self.modules_manager.selected_detectors_name))

        self.settings.child('scans', name).addChild(self.create_parameter(self.scanner.settings))
        self.settings.child('scans', name).addChild(self.create_parameter(self.scanner.get_scanner_sub_settings()))


class BatchScanner(QtCore.QObject):
    def __init__(self, area, actuators=[], detectors=[]):
        super().__init__()
        self.dockarea = area
        self.batchmanager = BatchManager(actuators=actuators, detectors=detectors, path=batch_path)

    @property
    def scans(self):
        return self.batchmanager.scans

    @property
    def scans_names(self):
        return self.batchmanager.get_scan_names()

    def get_scan(self, name: str):
        return self.batchmanager.get_scan(name)

    def get_act_dets(self):
        return self.batchmanager.get_act_dets()

    def setupUI(self):
        # %% create scan dock and make it a floating window
        self.batch_dock = Dock("BatchScanner", size=(1, 1), autoOrientation=False)  # give this dock the minimum possible size
        self.dockarea.addDock(self.batch_dock, 'left')
        self.batch_dock.float()

        self.widget = QtWidgets.QWidget()
        self.widget.setLayout(QtWidgets.QVBoxLayout())

        widget_infos = QtWidgets.QWidget()
        self.widget_infos_list = QtWidgets.QListWidget()
        widget_infos.setLayout(QtWidgets.QHBoxLayout())
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        widget_infos.layout().addWidget(splitter)
        splitter.addWidget(self.batchmanager.settings_tree)
        splitter.addWidget(self.widget_infos_list)
        self.batch_dock.addWidget(self.widget)
        self.widget.layout().addWidget(widget_infos)
        #self.create_menu()

    def create_menu(self, menubar=None):
        """
        """
        # %% create Settings menu
        if menubar is None:
            menubar = QtWidgets.QMenuBar()
            self.widget.layout().insertWidget(0, menubar)

        self.batch_menu = menubar.addMenu('Batch Configs')
        action_new = self.batch_menu.addAction('New Batch')
        action_new.triggered.connect(self.batchmanager.set_new_batch)
        action_modify = self.batch_menu.addAction('Modify Batch')
        action_modify.triggered.connect(self.batchmanager.set_file_batch)
        self.batch_menu.addSeparator()
        self.load_batch = self.batch_menu.addMenu('Load Batchs')

        slots = dict([])
        for ind_file, file in enumerate(batch_path.iterdir()):
            if file.suffix == '.xml':
                filestem = file.stem
                slots[filestem] = self.load_batch.addAction(filestem)
                slots[filestem].triggered.connect(
                    self.create_menu_slot(batch_path.joinpath(file)))

    def load_file(self, filepath=None):
        if filepath is None:
            path = file_io.select_file(start_path=batch_path, save=False, ext='xml')
            if path != '':
                filepath = path
            else:
                return
        self.batchmanager.set_file_batch(str(filepath), show=False)

        infos = self.batchmanager.set_scans()
        self.widget_infos_list.addItems(infos)

    def create_menu_slot(self, filename):
        return lambda: self.load_file(filename)


def main_batch_scanner():
    from pymodaq.control_modules.mocks import MockDAQMove, MockDAQViewer
    app = QtWidgets.QApplication(sys.argv)
    win = QtWidgets.QMainWindow()
    area = DockArea()
    win.setCentralWidget(area)

    # prog = BatchManager(msgbox=False, actuators=['Xaxis', 'Yaxis'], detectors=['Det0D', 'Det1D'])
    # prog.set_file_batch('C:\\Users\\weber\\pymodaq_local\\batch_configs\\batch_default.xml', show=False)
    # prog.set_scans()
    actuators = [MockDAQMove(title='Xaxis'), MockDAQMove(title='Yaxis')]
    detectors = [MockDAQViewer(title='Det0D'), MockDAQViewer(title='Det1D')]
    main = BatchScanner(area, actuators=actuators, detectors=detectors)
    main.setupUI()
    main.create_menu()
    win.show()
    sys.exit(app.exec_())


def main_batch_manager():
    from pymodaq.control_modules.mocks import MockDAQMove, MockDAQViewer
    app = QtWidgets.QApplication(sys.argv)
    actuators = [MockDAQMove(title='Xaxis'), MockDAQMove(title='Yaxis')]
    detectors = [MockDAQViewer(title='Det0D'), MockDAQViewer(title='Det1D')]
    prog = BatchManager(msgbox=True, actuators=actuators, detectors=detectors)
    sys.exit(app.exec_())


if __name__ == '__main__':
    #main_batch_manager()
    main_batch_scanner()
