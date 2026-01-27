from importlib import import_module
from pathlib import Path
from typing import Union

from qtpy import QtCore, QtWidgets
import qt_themes

from pymodaq_gui.utils import CustomApp
from pymodaq_gui.utils.widgets import LabelWithFont
from pymodaq_gui.utils.styling import create_icon

from pymodaq_utils.enums import StrEnum
from pymodaq_utils.utils import ThreadCommand
from pymodaq_utils.config import Config as ConfigUtils
from pymodaq.utils.config import Config

config_utils = ConfigUtils()
config = Config()


class ModuleActionIconNames(StrEnum):
    INIT = 'cable'
    SETTINGS = 'settings'
    SHOW_GRAPH = 'bid_landscape'
    SHOW_GRAPH_DISABLED = 'bid_landscape_disabled'

class ControlModuleUI(CustomApp):
    """ Base Class for ControlModules UIs

    Attributes
    ----------
    command_sig: Signal[Threadcommand]
        This signal is emitted whenever some actions done by the user has to be
        applied on the main module. Possible commands are:
        See specific implementation

    See Also
    --------
    :class:`daq_move_ui.DAQ_Move_UI`, :class:`daq_viewer_ui.DAQ_Viewer_UI`
    """
    command_sig = QtCore.Signal(ThreadCommand)

    # Common icon name for initialization action
    INIT_ICON = 'cable'

    def __init__(self, parent):
        super().__init__(parent)
        self.config = config
        self._ini_state = False

    def display_status(self, txt, wait_time=config_utils('general', 'message_status_persistence')):
        if self.statusbar is not None:
            self.statusbar.showMessage(txt, wait_time)

    def connect_things(self):
        self.connect_action('init', self.send_init)
        self.connect_action('show_settings', self.show_settings)               

    def update_init_icon(self, initialized: bool, action_name: str = 'init') -> None:
        """Update the initialization action icon based on state

        Parameters
        ----------
        initialized: bool
            Whether the module is initialized
        action_name: str
            The name of the init action
        """
        icon = create_icon(ModuleActionIconNames.INIT, icon_color=self.get_theme().green if initialized else self.get_theme().red)        
        if self.has_action(action_name):
            self.get_action(action_name).set_icon(icon)
        return icon
    
    def do_init(self, do_init=True):
        """Programmatically press the Init button
        API entry
        Parameters
        ----------
        do_init: bool
            will fire the Init button depending on the argument value and the button check state
        """
        if do_init is not self.is_action_checked('init'):
            self.get_action('init').trigger()

    def setup_statusbar(self, max_height: int = 30) -> QtWidgets.QStatusBar:
        """Create and configure a standard statusbar

        Parameters
        ----------
        max_height: int
            Maximum height of the statusbar in pixels

        Returns
        -------
        QtWidgets.QStatusBar
            The configured statusbar
        """
        self.statusbar = QtWidgets.QStatusBar()
        self.statusbar.setMaximumHeight(max_height)
        return self.statusbar

    def setup_title_widget(self, title: str, toolbar: QtWidgets.QToolBar = None,
                           font_name: str = "Tahoma", font_size: int = 14,
                           isbold: bool = True, isitalic: bool = True):
        """Add a styled title label to the toolbar

        Parameters
        ----------
        title: str
            The title text to display
        toolbar: QtWidgets.QToolBar
            The toolbar to add the label to (optional)
        font_name: str
            Font family name
        font_size: int
            Font size in points
        isbold: bool
            Whether to use bold font
        isitalic: bool
            Whether to use italic font

        Returns
        -------
        LabelWithFont
            The created label widget
        """
        label = LabelWithFont(title, font_name=font_name, font_size=font_size,
                              isbold=isbold, isitalic=isitalic)
        self.add_widget('name', label, toolbar=toolbar)
        return label

    def show_widget_with_close_handling(self, widget: QtWidgets.QWidget,
                                        show: bool, action_name: str):
        """Show/hide a widget and handle its close event to update action state

        Parameters
        ----------
        widget: QtWidgets.QWidget
            The widget to show/hide
        show: bool
            Whether to show or hide the widget
        action_name: str
            The name of the action to uncheck when widget is closed
        """
        widget.setVisible(show)
        widget.closeEvent = lambda event: self.set_action_checked(action_name, False)


    def _set_init_state(self, status: bool):
        self._ini_state = status
        self.enable_actions(status, all_except=('init', 'selector', 'show_settings', 'show_graphs'))
        try:
            self.set_action_enabled('selector', not status)
        except Exception:
            pass
        self.update_init_icon(status, 'init')

    def enable_actions(self, status=True, all_except=()):
        for action in self.actions_names:
            if action not in all_except:
                self.set_action_enabled(action, status)

    def send_init(self, checked: bool):
        """Should be implemented to send to the main app the fact that someone (un)checked init."""
        raise NotImplementedError

    def show_settings(self, show: bool = True):
        """Show or hide the settings widget

        Parameters
        ----------
        show: bool
            Whether to show or hide the settings widget
        """
        self.show_widget_with_close_handling(
            self.settings_tree, show, 'show_settings')

    def setup_init_action(self, action_name: str = 'init', label: str = 'Initialize',
                          toolbar: QtWidgets.QToolBar = None):
        """Add a standard initialization action to the toolbar

        Parameters
        ----------
        action_name: str
            The name/key for the action
        label: str
            The display label for the action
        toolbar: QtWidgets.QToolBar
            The toolbar to add the action to (optional)

        Returns
        -------
        The created action
        """
        return self.add_action(action_name, label, ModuleActionIconNames.INIT,
                               checkable=True, toolbar=toolbar,
                               tip='Connect to selected module',
                               icon_color=self.get_theme().red,
                               icon_checked_color=self.get_theme().green)

    def setup_settings_action(self, action_name: str = 'show_settings',
                              toolbar: QtWidgets.QToolBar = None):
        """Add a standard show settings action to the toolbar

        Parameters
        ----------
        action_name: str
            The name/key for the action
        toolbar: QtWidgets.QToolBar
            The toolbar to add the action to (optional)

        Returns
        -------
        The created action
        """
        return self.add_action(action_name, 'Show Settings', ModuleActionIconNames.SETTINGS,
                               "Show Settings", checkable=True, toolbar=toolbar,
                               icon_checked_color=self.get_theme().green)

    def setup_show_graph_action(self, action_name: str = 'show_graph',
                                label: str = 'Show Graph',
                                tip: str = 'Show/Hide the Graph Widget',
                                toolbar: QtWidgets.QToolBar = None):
        """Add a standard show graph action to the toolbar

        Parameters
        ----------
        action_name: str
            The name/key for the action
        label: str
            The display label for the action
        tip: str
            The tooltip for the action
        toolbar: QtWidgets.QToolBar
            The toolbar to add the action to (optional)

        Returns
        -------
        The created action
        """
        return self.add_action(action_name, label, ModuleActionIconNames.SHOW_GRAPH, tip,
                               checkable=True,
                               icon_checked=ModuleActionIconNames.SHOW_GRAPH_DISABLED,
                               icon_color=self.get_theme().green,
                               icon_checked_color=self.get_theme().red,
                               toolbar=toolbar)


def register_uis(parent_module_name: str = 'pymodaq.control_modules.daq_move_ui'):
    uis = []
    try:
        module = import_module(f'{parent_module_name}.uis')

        path = Path(module.__path__[0])

        for file in path.iterdir():
            if file.is_file() and 'py' in file.suffix and file.stem != '__init__':
                try:
                    uis.append(import_module(f'.{file.stem}', module.__name__))
                except (ModuleNotFoundError, Exception) as e:
                    pass
    except ModuleNotFoundError:
        pass
    finally:
        return uis
