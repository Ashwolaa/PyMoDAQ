# -*- coding: utf-8 -*-
"""
Created the 05/09/2022

@author: Sebastien Weber
"""


from typing import List, Union
import sys

from qtpy import QtWidgets, QtCore
from qtpy.QtCore import Signal
from qtpy.QtWidgets import QVBoxLayout

from pymodaq.utils.daq_utils import ThreadCommand
from pymodaq.control_modules.ui_utils import ControlModuleUI

from pymodaq_gui.utils.widgets import QLED
from pymodaq_gui.utils import DockArea
from pymodaq_utils.config import Config as ConfigUtils
from pymodaq_utils.enums import StrEnum
from pymodaq_gui.plotting.data_viewers.viewer import ViewerFactory, ViewerDispatcher
from pymodaq_gui.plotting.data_viewers import ViewersEnum
from pymodaq_gui.utils.styling import create_icon
from pymodaq.utils.config import Config
from pymodaq.control_modules.thread_commands import UiToMainViewer
from pymodaq.control_modules.daq_viewer_ui.viewer_selector import SelectedDetector, ViewerSelector, get_detector_menu_entries

viewer_factory = ViewerFactory()
config = Config()
config_utils = ConfigUtils()



class ActionIconNames(StrEnum):
    SNAP = 'looks_one'
    GRAB = 'repeat'
    GRAB_STOP = 'repeat_on'
    INI = 'cable'


class DAQ_Viewer_UI(ControlModuleUI, ViewerDispatcher):
    """DAQ_Viewer user interface.

    This class manages the UI and emit dedicated signals depending on actions from the user

    Attributes
    ----------
    command_sig: Signal[Threadcommand]
        This signal is emitted whenever some actions done by the user has to be
        applied on the main module. Possible commands are:
            * init
            * grab
            * snap
            * detector_changed
            * daq_type_changed
            * save_current

    Methods
    -------
    display_value(value: float)
        Update the display of the actuator's value on the UI
    do_init()
        Programmatic init

    See Also
    --------
    pymodaq.utils.daq_utils.ThreadCommand
    """

    command_sig = Signal(ThreadCommand)

    def __init__(self, parent: QtWidgets.QWidget, title="DAQ_Viewer", settings_tree=None, **kwargs):
        super().__init__(parent, settings_tree)
        self.dockarea = DockArea()

        ViewerDispatcher.__init__(self, self.dockarea, title=title)

        self.title = title

        self._ini_state = False
        self._data_ready = False

        self.selector = ViewerSelector(add_menu_entries=get_detector_menu_entries())
        self.statusbar: QtWidgets.QStatusBar = None
        self.grab_done_led: QLED = None

        self.setup_docks()

        self.setup_actions()  # see ActionManager MixIn class
        self.update_viewers([self.selector.selected_module.daq_type.to_viewer_type()])
        self.connect_things()

        self.enable_actions(False, all_except=('init', 'selector', 'show_settings', 'show_graph'))
        self.settings_tree.setVisible(False)

    @property
    def detector(self) -> SelectedDetector:
        return self.selector.selected_module

    @detector.setter
    def detector(self, det: SelectedDetector):
        self.selector.selected_module = det

    def close(self):
        for dock in self.viewer_docks:
            dock.close()
        self.settings_tree.close()

    def setup_docks(self):
        widget = self.parent

        widget.setLayout(QVBoxLayout())
        widget.layout().setContentsMargins(2, 2, 2, 2)
        widget.layout().addWidget(self.dockarea)

        self.setup_statusbar()
        self.grab_done_led = QLED(readonly=True)

    def setup_actions(self):
        self.setup_title_widget(self.title)
        self.add_widget('selector', self.selector.add_widget)
        self.setup_init_action(label='Ini. Detector')
        self.setup_settings_action()
        self.setup_show_graph_action('show_graph', 'Show Graphs', 'Show/Hide the Graphs Area')        
        self.toolbar.addSeparator()
        self.add_widget('grab_done', self.grab_done_led)
        self.toolbar.addSeparator()
        self.add_action('snap', 'Snap', ActionIconNames.SNAP, "Take a snapshot from the detector")
        self.add_action('grab', 'Grab', ActionIconNames.GRAB, "Grab data from the detector", checkable=True,
                        icon_checked=ActionIconNames.GRAB_STOP,
                        icon_checked_color=self.get_theme().green)
        self.add_action('save_current', 'Save Current Data', 'save_as', "Save Current Data")
        self.toolbar.addSeparator()
        self.add_action('background_snap', 'Snap Background', 'background_replace',
                        tip='Take a snapshot a set it as background')
        self.add_action('background_subtract', 'Subtract Background', 'texture_minus', checkable=True,
                        tip='If checked, apply background substraction',
                        icon_checked_color=self.get_theme().green)
        self.add_widget('status', self.statusbar)

    def connect_things(self):
        super().connect_things()                
        self.connect_action('grab', self._grab)
        self.connect_action('snap', lambda: self.command_sig.emit(ThreadCommand(UiToMainViewer.SNAP, )))
        self.connect_action('save_current', lambda: self.command_sig.emit(ThreadCommand(UiToMainViewer.SAVE_CURRENT, )))
        self.selector.module_changed.connect(self._detector_changed)
        self.connect_action('background_subtract',
                            lambda checked: self.command_sig.emit(ThreadCommand(UiToMainViewer.DO_BKG, checked)))
        self.connect_action('background_snap',
                            lambda: self.command_sig.emit(ThreadCommand(UiToMainViewer.TAKE_BKG)))
        self.connect_action('show_graph', lambda checked: self.show_graph(not checked))

    def show_graph(self, show: bool = True):
        self.show_widget_with_close_handling(self.parent, show, 'show_graph')

    def update_viewers(self, viewers_type: List[Union[str, ViewersEnum]],
                       viewers_name: List[str] = None, force=False):
        super().update_viewers(viewers_type)
        self.command_sig.emit(ThreadCommand(UiToMainViewer.VIEWERS_CHANGED,
                                            attribute=dict(viewer_types=self.viewer_types,
                                                           viewers=self.viewers)))
    @property
    def grab_done(self):
        """bool: the status of the grab_done LED."""
        return self.grab_done_led.get_state()

    @grab_done.setter
    def grab_done(self, status):
        self.grab_done_led.set_as(status)

    @property
    def data_ready(self):
        return self._data_ready

    @data_ready.setter
    def data_ready(self, status):
        self._data_ready = status
        if status:
            icon = create_icon(ActionIconNames.SNAP,
                               icon_color=self.get_theme().green,)
        else:
            icon = create_icon(ActionIconNames.SNAP,
                               icon_color=self.get_theme().red,)
        self.get_action('snap').set_icon(icon)

    def _detector_changed(self, sel_mod: SelectedDetector):
        try:
            self.command_sig.emit(ThreadCommand(UiToMainViewer.DETECTOR_CHANGED, sel_mod))
            if self.viewer_types != [sel_mod.daq_type.to_viewer_type()]:
                self.update_viewers([sel_mod.daq_type.to_viewer_type()])
        except ValueError as e:
            pass

    def _grab(self):
        """Slot from the *grab* action"""
        self.command_sig.emit(ThreadCommand(UiToMainViewer.GRAB, attribute=self.is_action_checked('grab')))
        self.enable_actions(not self.is_action_checked('grab'),
                            all_except=('grab', 'selector', 'show_settings', 'show_graph'))

        if not self.config('viewer', 'allow_settings_edition'):
            self.settings_tree.setEnabled(not self.is_action_checked('grab'))

    ################ Trigger actions ################            

    def do_grab(self, do_grab=True):
        """Programmatically press the Grab button
        API entry
        Parameters
        ----------
        do_grab: bool
            will fire the Init button depending on the argument value and the button check state
        """
        if (do_grab and not self.is_action_checked('grab')) or ((not do_grab) and self.is_action_checked('grab')):
            self.get_action('grab').trigger()

    def do_snap(self):
        """Programmatically press the Snap button
        API entry
        """
        self.get_action('snap').trigger()

    def do_stop(self):
        """Programmatically uncheck the grab button
        API entry
        """
        if self.is_action_checked('grab'):
            self.get_action('grab').trigger()

    def send_init(self, checked: bool):
        self.selector.add_widget.setEnabled(not checked)
        if not checked and self.is_action_checked('background_subtract'):
            self.get_action('background_subtract').trigger()
        QtWidgets.QApplication.processEvents()
        self.command_sig.emit(ThreadCommand(UiToMainViewer.INIT,
                                            [checked,
                                             self.selector.selected_module]))

    def _enable_detchoices(self, enable=True):
        self.get_action('selector').widget.setEnabled(enable)

    @property
    def detector_init(self):
        """bool: the internal init status."""
        return self._ini_state

    @detector_init.setter
    def detector_init(self, status):
        self._set_init_state(status)


def main(init_qt=True):
    from pymodaq_gui.parameter import Parameter
    from pymodaq.control_modules.viewer_utility_classes import params as daq_viewer_params
    from pymodaq.utils.shared_ui import SharedUI
    from pymodaq_gui.qt_utils import mkQApp

    if init_qt:  # used for the test suite
        app = mkQApp("PyMoDAQ UI Viewer")

    param = Parameter.create(name='settings', type='group', children=daq_viewer_params)



    widget = QtWidgets.QWidget()
    prog = DAQ_Viewer_UI(widget, title='myViewer')
    shared_ui = SharedUI(widget)

    timer = QtCore.QTimer(shared_ui)

    def set_data_ready(ready=True):
        prog.data_ready = True

    def set_data_ready_loop(ready=True):
        prog.data_ready = True
        app.processEvents()
        QtCore.QThread.msleep(100)
        prog.data_ready = False
        app.processEvents()

    def print_command_sig(cmd_sig):
        print(cmd_sig)
        prog.display_status(str(cmd_sig))
        if cmd_sig.command == UiToMainViewer.INIT:
            prog.detector_init = cmd_sig.attribute[0]
        elif cmd_sig.command == UiToMainViewer.SNAP:
            prog.data_ready = False
            timer.timeout.connect(set_data_ready)
            timer.setSingleShot(True)
            timer.start(500)

        elif cmd_sig.command == UiToMainViewer.GRAB:
            prog.data_ready = False
            if cmd_sig.attribute:
                timer.timeout.connect(set_data_ready_loop)
                timer.setSingleShot(False)
                timer.start(500)
            else:
                timer.stop()


    # prog.detectors = detectors
    prog.command_sig.connect(print_command_sig)

    #prog.update_viewers([prog.selector.selected_module.daq_type.to_viewer_type()])

    shared_ui.add_toolbar('viewer', 'Viewer', toolbar=prog.toolbar, add_break=True)

    shared_ui.show()


    if init_qt:
        sys.exit(app.exec())


if __name__ == '__main__':
    main()
