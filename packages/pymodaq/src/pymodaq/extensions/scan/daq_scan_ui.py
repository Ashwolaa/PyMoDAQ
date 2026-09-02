# -*- coding: utf-8 -*-
"""
Created the 06/12/2022

@author: Sebastien Weber
"""
from typing import List, TYPE_CHECKING

from qtpy import QtWidgets, QtCore
from qtpy.QtCore import Signal


from pymodaq_gui.utils.shared_ui import MenuToolbarNames
from pymodaq_utils.utils import ThreadCommand
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq_gui.utils import CustomApp
from pymodaq_gui.utils import Dock
from pymodaq_gui.utils.widgets.spinbox import QSpinBox_ro
from pymodaq_gui.utils.widgets import QLED
from pymodaq_gui.plotting.data_viewers.viewer import ViewerDispatcher
from pymodaq_gui.plotting.data_viewers import ViewersEnum
from pymodaq_gui.parameter import ParameterTree


if TYPE_CHECKING:

    from pymodaq.extensions.scan.daq_scan import DAQScan

logger = set_logger(get_module_name(__file__))


class DAQScanUI(CustomApp, ViewerDispatcher):
    """

    """
    command_sig = Signal(ThreadCommand)

    def __init__(self, parent, toolbar=None):
        CustomApp.__init__(self, parent, toolbar=toolbar, add_toolbar_break=False)
        self.setup_docks_and_widgets()
        ViewerDispatcher.__init__(self, self.dockarea, title='Scanner',
                                  next_to_dock=self.dock_command)

        self.setup_menus_and_toolbars(self.menubar)
        self.setup_actions()
        self.connect_things()

    def enable_start_stop(self, enable=True):
        """If True enable main buttons to launch/stop scan"""
        self.set_action_enabled('start', enable)
        self.set_action_enabled('stop', enable)
        self.set_action_enabled('pause', enable)
        if enable:
            self.set_action_checked('pause', False)

    def setup_docks_and_widgets(self):
        self.dock_command = Dock('Scan Command')
        self.dockarea.addDock(self.dock_command)

        widget_command = QtWidgets.QWidget()
        widget_command.setLayout(QtWidgets.QVBoxLayout())
        self.dock_command.addWidget(widget_command)

        splitter_widget = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        widget_command.layout().addWidget(splitter_widget)

        # Column 1: Actuators (selection + probe, and scan geometry)
        self.actuators_widget = self._make_section_groupbox('Actuators')
        self.actuators_widget.setMinimumWidth(220)
        self.actuators_widget.setMaximumWidth(400)

        self.actuators_settings_tree = ParameterTree()
        self.actuators_widget.layout().addWidget(self.actuators_settings_tree)

        self.actuators_widget.layout().addWidget(self._section_label('Scan Parameters'))
        self.scanner_widget = QtWidgets.QWidget()
        self.scanner_widget.setLayout(QtWidgets.QVBoxLayout())
        self.actuators_widget.layout().addWidget(self.scanner_widget)

        # Column 2: Detectors (selection + probe, and what/how to plot from them)
        self.detectors_widget = self._make_section_groupbox('Detectors')
        self.detectors_widget.setMinimumWidth(220)
        self.detectors_widget.setMaximumWidth(400)

        self.detectors_settings_tree = ParameterTree()
        self.detectors_widget.layout().addWidget(self.detectors_settings_tree)

        self.detectors_widget.layout().addWidget(self._section_label('Plotting Parameters'))
        self.plotting_settings_tree = ParameterTree()
        self.detectors_widget.layout().addWidget(self.plotting_settings_tree)

        # Column 3: General (infrequently-touched, cross-cutting settings, including Save)
        self.general_widget = self._make_section_groupbox('General')
        self.general_widget.setMinimumWidth(220)
        self.general_widget.setMaximumWidth(400)

        self.general_settings_tree = ParameterTree()
        self.general_widget.layout().addWidget(self.general_settings_tree)

        splitter_widget.addWidget(self.actuators_widget)
        splitter_widget.addWidget(self.detectors_widget)
        splitter_widget.addWidget(self.general_widget)
        splitter_widget.setSizes([300, 300, 300])

        self.populate_status_bar()

    @staticmethod
    def _make_section_groupbox(title: str) -> QtWidgets.QGroupBox:
        """A QGroupBox whose title is bold, larger and centered, for clear section identification"""
        box = QtWidgets.QGroupBox(title)
        box.setLayout(QtWidgets.QVBoxLayout())
        box.layout().setContentsMargins(8, 18, 8, 8)
        box.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        box.setStyleSheet(
            'QGroupBox { font-weight: bold; font-size: 11pt; margin-top: 6px; } '
            'QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; '
            'padding: 0 6px; }')
        return box

    @staticmethod
    def _section_label(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        label.setStyleSheet('font-weight: bold; font-size: 10pt;')
        return label

    @staticmethod
    def _content_fit_height(tree: ParameterTree, hard_limit: int = 250, min_height: int = 60) -> int:
        """ Height needed to show all of a populated tree's current (non-collapsed) rows
        without a scrollbar, capped at hard_limit rather than guessed """
        tree.expandAll()
        tree.doItemsLayout()
        if tree.topLevelItemCount() == 0:
            return min_height
        last_item = tree.topLevelItem(tree.topLevelItemCount() - 1)
        while last_item.childCount() > 0:
            last_item = last_item.child(last_item.childCount() - 1)
        bottom = tree.visualItemRect(last_item).bottom()
        header_height = 0 if tree.header().isHidden() else tree.header().height()
        content_height = header_height + bottom + 2 * tree.frameWidth() + 4
        return max(min_height, min(content_height, hard_limit))

    def setup_menus_and_toolbars(self, menubar: QtWidgets.QMenuBar = None):
        from pymodaq.extensions.scan.manager.scan_manager import ScanManager
        self.add_menu(MenuToolbarNames.FILE, MenuToolbarNames.FILE.capitalize(), parent_menu=menubar)
        self.add_menu(MenuToolbarNames.TOOLS, MenuToolbarNames.TOOLS.capitalize(), parent_menu=menubar)
        self.add_menu('actions', 'Actions', parent_menu=menubar)

        self.add_toolbar('scan_manager', 'Scan Manager', parent=self.mainwindow,
                         add_break=False)
        self.add_menu('scan_manager', 'Scan Manager', MenuToolbarNames.TOOLS, icon_name=ScanManager.icon_name)

    def setup_actions(self):
        self.add_action('ini_positions', 'Init Positions', 'arrows_input', menu='actions')
        self.set_action_enabled('ini_positions', False)
        self.add_action('start', 'Start Scan', 'motion_play', "Start the scan",
                        menu='actions', icon_color=self.get_theme().green)
        self.add_action('start_batch', 'Start ScanBatches', 'run_all', "Start the batch of scans", menu='actions')
        self.add_action('stop', 'Stop Scan', 'stop_circle', "Stop the scan",
                        menu='actions', icon_color=self.get_theme().red)
        self.add_action('pause', 'Pause Scan', 'pause_circle', "Pause/resume the scan",
                        checkable=True, menu='actions',
                        icon_checked_color=self.get_theme().orange)
        self.add_action('move_at', 'Move at doubleClicked', 'moving',
                        "Move to positions where you double clicked", checkable=True, menu='actions')

        self._toolbar.addSeparator()
        self.add_action('show_file', 'Show file content', 'folder_data',
                        tip='Browse the content of the current HDF5 file')

        self.add_action('new_file', 'New file', 'new2', menu=MenuToolbarNames.FILE, auto_toolbar=False)
        self.add_action('load', 'Open file to append...', 'Open', menu=MenuToolbarNames.FILE, auto_toolbar=False)
        self.get_menu(MenuToolbarNames.FILE).addSeparator()
        self.add_action('save', 'Save copy as...', 'SaveAs', menu=MenuToolbarNames.FILE, auto_toolbar=False)
        # Debug-only actions: registered but not in any menu so they stay hidden from regular users.
        # A developer can access them programmatically or add them back to a menu as needed.
        self.add_action('open_file', 'Open current file', '', auto_toolbar=False)
        self.add_action('close_file', 'Close current file', '', auto_toolbar=False)

        self.add_action('navigator', 'Show Navigator', '', menu=MenuToolbarNames.TOOLS, auto_toolbar=False)
        self.add_action('batch', 'Show Batch Scanner', '', menu=MenuToolbarNames.TOOLS, auto_toolbar=False)
        self.add_action('show_viewers', 'Show/Hide Viewers', 'DAQ_Viewer_pannel',
                        tip='Show or hide the independent window holding the live plot viewers',
                        menu=MenuToolbarNames.TOOLS)
        self.set_action_visible('start_batch', False)

    def connect_things(self):
        self.connect_action('ini_positions', lambda: self.command_sig.emit(ThreadCommand('ini_positions')))
        self.connect_action('start', lambda: self.command_sig.emit(ThreadCommand('start')))
        self.connect_action('start_batch', lambda: self.command_sig.emit(ThreadCommand('start_batch')))
        self.connect_action('stop', lambda: self.command_sig.emit(ThreadCommand('stop')))
        self.connect_action('pause', lambda: self.command_sig.emit(ThreadCommand('pause')))
        self.connect_action('move_at', lambda: self.command_sig.emit(ThreadCommand('move_at')))

        self.connect_action('new_file', lambda: self.command_sig.emit(ThreadCommand('new_file')))
        self.connect_action('load', lambda: self.command_sig.emit(ThreadCommand('load')))
        self.connect_action('save', lambda: self.command_sig.emit(ThreadCommand('save')))
        self.connect_action('show_file', lambda: self.command_sig.emit(ThreadCommand('show_file')))
        self.connect_action('open_file', lambda: self.command_sig.emit(ThreadCommand('open_file')))
        self.connect_action('close_file', lambda: self.command_sig.emit(ThreadCommand('close_file')))
        self.connect_action('navigator', lambda: self.command_sig.emit(ThreadCommand('navigator')))
        self.connect_action('batch', lambda: self.command_sig.emit(ThreadCommand('batch')))
        self.connect_action('show_viewers', lambda: self.command_sig.emit(ThreadCommand('show_viewers')))

    def finalize_ui(self, app: 'DAQScan'):
        app.create_dashboard_toolbar(add_break=False)

        self.set_scanner_settings(app.scanner.parent_widget)

        self.actuators_settings_tree.addParameters(app.modules_manager.settings.child('actuators'))
        self.actuators_settings_tree.addParameters(app.modules_manager.settings.child('test_actuator'))

        self.detectors_settings_tree.addParameters(app.modules_manager.settings.child('detectors'))
        self.detectors_settings_tree.addParameters(app.modules_manager.settings.child('probe_data'))

        selection_tree_height = max(self._content_fit_height(self.actuators_settings_tree),
                                    self._content_fit_height(self.detectors_settings_tree))
        self.actuators_settings_tree.setFixedHeight(selection_tree_height)
        self.detectors_settings_tree.setFixedHeight(selection_tree_height)

        self.plotting_settings_tree.setParameters(app.settings.child('plot_options'))

        self.general_settings_tree.addParameters(app.settings.child('time_flow'))
        self.general_settings_tree.addParameters(app.settings.child('scan_options'))

        app._h5saver.settings.setOpts(title='Save')
        self.general_settings_tree.addParameters(app._h5saver.settings)

        for ind_menu, menu in enumerate(self.menus):
            app.reference_menu(self.menus_names[ind_menu], menu)

        for ind_toolbar, toolbar in enumerate(self.toolbars):
            app.reference_toolbar(self.toolbars_names[ind_toolbar], toolbar)

        self.enable_start_stop(False)

    def add_scanner_settings(self, tree: 'ParameterTree'):
        """Adds a  ParameterTree to the Scanner settings widget"""
        self.scanner_widget.layout().addWidget(tree)

    def set_scanner_settings(self, settings_tree: QtWidgets.QWidget):
        while True:
            child = self.scanner_widget.layout().takeAt(0)
            if not child:
                break
            child.widget().deleteLater()
            QtWidgets.QApplication.processEvents()

        self.scanner_widget.layout().addWidget(settings_tree)

    def populate_status_bar(self):
        self._status_message_label = QtWidgets.QLabel('Initializing')
        self._n_scan_steps_sb = QSpinBox_ro()
        self._n_scan_steps_sb.setToolTip('Total number of steps')
        self._indice_scan_sb = QSpinBox_ro()
        self._indice_scan_sb.setToolTip('Current step value')
        self._indice_average_sb = QSpinBox_ro()
        self._indice_average_sb.setToolTip('Current average value')
        
        self._scan_done_LED = QLED()
        self._scan_done_LED.set_as_false()
        self._scan_done_LED.clickable = False
        self._scan_done_LED.setToolTip('Scan done state')

        self._file_open_LED = QLED()
        self._file_open_LED.set_as_false()
        self._file_open_LED.clickable = False
        self._file_open_LED.setToolTip('H5 file open and accessible')

        self._swmr_label = QtWidgets.QLabel('')
        self._swmr_label.setToolTip('SWMR mode status')
        self._swmr_label.setVisible(False)

        self.statusbar.addPermanentWidget(self._status_message_label)

        self.statusbar.addPermanentWidget(self._n_scan_steps_sb)
        self.statusbar.addPermanentWidget(self._indice_scan_sb)
        self.statusbar.addPermanentWidget(self._indice_average_sb)
        self._indice_average_sb.setVisible(False)
        self.statusbar.addPermanentWidget(self._scan_done_LED)
        self.statusbar.addPermanentWidget(QtWidgets.QLabel('File:'))
        self.statusbar.addPermanentWidget(self._file_open_LED)
        self.statusbar.addPermanentWidget(self._swmr_label)

    @property
    def n_scan_steps(self):
        return self._n_scan_steps_sb.value()

    @n_scan_steps.setter
    def n_scan_steps(self, nsteps: int):
        self._n_scan_steps_sb.setValue(nsteps)

    def set_permanent_status(self, status: str):
        self._status_message_label.setText(status)

    def set_scan_step(self, step_ind: int):
        self._indice_scan_sb.setValue(step_ind)

    def show_average_step(self, show: bool = True):
        self._indice_average_sb.setVisible(show)

    def set_scan_step_average(self, step_ind: int):
        self._indice_average_sb.setValue(step_ind)

    def set_scan_done(self, done=True):
        self._scan_done_LED.set_as(done)

    def set_file_open(self, is_open: bool):
        """Update the file-open status LED.

        Parameters
        ----------
        is_open:
            True (green) if the h5 file is open and accessible, False (red) otherwise.
        """
        self._file_open_LED.set_as(is_open)

    def set_swmr_status(self, active: bool, compatible: bool = False):
        """Show or hide the SWMR mode indicator in the status bar.

        Parameters
        ----------
        active:
            True if SWMR mode is currently active on the file.
        compatible:
            True if the file was created with SWMR support.
        """
        if active:
            self._swmr_label.setText('SWMR')
            self._swmr_label.setToolTip('SWMR mode active')
            self._swmr_label.setVisible(True)
        elif compatible:
            self._swmr_label.setText('SWMR file')
            self._swmr_label.setToolTip('File created with SWMR support')
            self._swmr_label.setVisible(True)
        else:
            self._swmr_label.setText('')
            self._swmr_label.setToolTip('SWMR mode status')
            self._swmr_label.setVisible(False)

    def update_viewers(self, viewers_type: List[ViewersEnum], viewers_name: List[str] = None, force=False):
        super().update_viewers(viewers_type, viewers_name, force)
        self.command_sig.emit(ThreadCommand('viewers_changed', attribute=dict(viewer_types=self.viewer_types,
                                                                              viewers=self.viewers)))

