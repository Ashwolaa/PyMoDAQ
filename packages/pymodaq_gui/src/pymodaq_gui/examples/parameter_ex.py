"""
S Weber  2020
Examples of custome parameter types derived from pyqtgraph
"""
import sys
from qtpy import QtWidgets, QtCore
from collections import OrderedDict

import pymodaq_gui.utils.widgets.table as table
from pymodaq_gui.utils.utils import create_nested_menu
from pymodaq_gui.parameter.pymodaq_ptypes import GroupParameter, registerParameterType
from pymodaq_gui.managers.parameter_manager import ParameterManager

class ScalableGroup(GroupParameter):
    def __init__(self, **opts):
        super().__init__(**opts)

    def addNew(self, full_path:tuple):
        # Full_path contains all the sub menus
        value = full_path[-1] # Only showing last values as a string
        self.addChild(dict(name=f"ScalableParam {(len(self.childs)+1)}", type='str', value=value, removable=True, renamable=True))

# Need to register a new type to properly trigger addNew
registerParameterType('groupedit', ScalableGroup, override=True)

def create_text_with_pattern_parameter():
    text_params = {
                "name": "text_with_pattern",
                "title": "Text Editing with pattern completion (@ for users, # for languages):",
                "type": "text_pattern",
                "value": "",
                "patterns": {
                    "@": ["alice", "bob", "charlie"],
                    "#": ["python", "javascript", "cpp"],
                },
                "completer_config": {
                    "min_width": 200,
                    "max_width": 400,
                    "case_sensitive": False,
                    "visual_indicator": True,
                },
            }

    return text_params

class ParameterEx(ParameterManager):
    params = [
        {'title': 'Groups:', 'name': 'groups', 'type': 'group', 'children': [
            {'title': 'A visible group:', 'name': 'agroup', 'type': 'group', 'children': []},
            {'title': 'An hidden group:', 'name': 'bgroup', 'type': 'group', 'children': [], 'visible': False},  # this visible option is not available in usual pyqtgraph group     
            {'title': 'An expandable group:', 'name': 'cgroup', 'type': 'groupedit', 'addText': 'Add', 'addMenu':
              create_nested_menu(3,3,'Menu','Sub',use_index_tracking=True)},
            {'title': 'A bool with children:', 'name': 'booleans_group', 'type': 'bool', 'value':False, 'tip': 'Any Parameter can have its own children', 'children': [
            {'title': 'A bool in a bool', 'name': 'a_bool_in_a_bool', 'type': 'bool', 'value': True},
            {'title': 'A push with children', 'name': 'aboolpush', 'type': 'bool_push', 'value': True, 'label': 'action','children':[
                 {'title': 'A string in a group', 'name': 'atte_in_a_group', 'type': 'str', 'value': 'this is a string you can edit'},
            ]},]},
        ]},
        {'title': 'Numbers:', 'name': 'numbers', 'type': 'group', 'children': [
            {'title': 'Standard float', 'name': 'afloat', 'type': 'float', 'value': 20., 'min': 1.,
             'tip': 'displays this text as a tooltip'},
            {'title': 'Another float', 'name': 'anotherfloat', 'type': 'float', 'value': 123., 'min': 1.,
             'tip': 'displays this text as a tooltip'},
            {'title': 'Linear Slide float', 'name': 'linearslidefloat', 'type': 'slide',
             'value': 50, 'default': 50, 'min': 0, 'max': 123, 'subtype': 'linear'},
            {'title': 'Linear Slide float w limits', 'name': 'linearslidefloatlimits',
             'type': 'slide', 'value': 50, 'default': 50, 'limits': (24, 123), 'subtype': 'linear'},
            {'title': 'Linear int Slide', 'name': 'linearslideint', 'type': 'slide', 'value': 50, 'default': 50, 'step':1,
             'min': 0,
             'max': 123, 'subtype': 'linear', 'int': True},
            {'title': 'Linear Slide with suffix', 'name': 'linearslidewithsuffixandsiPrefix', 'type': 'slide', 'value': 50, 'default': 50,
             'min': 0,
             'max': 1e6, 'subtype': 'linear','suffix':'V','siPrefix':True},
            {'title': 'Log Slide float', 'name': 'logslidefloat', 'type': 'slide', 'value': 50, 'default': 50,
             'min': 1e-5,
             'max': 1e5, 'subtype': 'log','suffix':'V','siPrefix':True},
        ]},

        {'title': 'Booleans:', 'name': 'booleans', 'type': 'group', 'children': [
            {'title': 'Standard bool', 'name': 'abool', 'type': 'bool', 'value': True},
            {'title': 'bool push', 'name': 'aboolpush', 'type': 'bool_push', 'value': True, 'label': 'action'},
            {'title': 'A led', 'name': 'aled', 'type': 'led', 'value': False, 'tip': 'a led you cannot toggle'},
            {'title': 'A led', 'name': 'anotherled', 'type': 'led_push', 'value': True, 'tip': 'a led you can toggle'},
            {'title': 'Action + LED', 'name': 'anactionled', 'type': 'action_led', 'value': False,
             'tip': 'Button fires sigActivated; LED value reflects done state. label opt sets button text.',
             'label': 'Run'},
        ]},

        {'title': 'DateTime:', 'name': 'datetimes', 'type': 'group', 'children': [
            {'title': 'Time:', 'name': 'atime', 'type': 'time', 'value': QtCore.QTime.currentTime()},
            {'title': 'Date:', 'name': 'adate', 'type': 'date', 'value': QtCore.QDate.currentDate(),
             'format': 'dd/MM/yyyy'},
            {'title': 'DateTime:', 'name': 'adatetime', 'type': 'date_time',
             'value': QtCore.QDateTime(QtCore.QDate.currentDate(), QtCore.QTime.currentTime()),
             'format': 'MM/dd/yyyy hh:mm', 'tip': 'displays this text as a tooltip'},
        ]},
        {'title': 'An action', 'name': 'action', 'type': 'action'},  # action whose displayed text corresponds to title

        {'title': 'Lists:', 'name': 'lists', 'type': 'group', 'children': [
            {'title': 'Standard list:', 'name': 'alist', 'type': 'list',
             'limits': ['a value', 'another one'], 'value': 'a value'},
            {'title': 'List with add:', 'name': 'anotherlist', 'type': 'list',
             'limits': ['a value', 'another one'], 'value': 'a value',
             'show_pb': True, 'tip': 'when using the "show_pb" option, displays a plus button to add elt to the list'},
            {'title': 'List defined from a dict:', 'name': 'dict_list', 'type': 'list',
             'limits': {'xaxis': 0, 'yaxis': [0, 1, 2]},
             'value': 'yaxis',
             'tip': 'Such a parameter display text that are keys of a dict while'
                                                        'values could be any object'
             },
        ]},
        {'title': 'Browsing files:', 'name': 'browser', 'type': 'group', 'children': [
            {'title': 'Look for a file:', 'name': 'afile', 'type': 'browsepath', 'value': r'D:\Data', 'filetype': True,
             'tip': 'If filetype is True select a file otherwise a directory'},
            {'title': 'Look for a dir:', 'name': 'adir', 'type': 'browsepath', 'value': r'D:\Databis', 'filetype': False,
             'tip': 'If filetype is True select a file otherwise a directory'},

        ]},
        {'title': 'Selectable items:', 'name': 'itemss', 'type': 'group', 'children': [
            {'title': 'Selectable items', 'name': 'items', 'type': 'itemselect',
             'value': dict(all_items=['item1', 'item2', 'item3', 'item4', 'item5'],
                           selected=['item2']),
             'tip': 'Press Ctrl+click  to select items in any order'},
            {'title': 'Selectable items', 'name': 'itemsbis', 'type': 'itemselect',
             'value': dict(all_items=['item1', 'item2', 'item3'], selected=['item2']),
             'tip': 'If show_pb is True, user can add items to the list', 'show_pb': True,},
            {'title': 'Removable items', 'name': 'itemsbisbis', 'type': 'itemselect',
             'value': dict(all_items=['item1', 'item2', 'item3'], selected=['item2']),
             'tip': 'If show_mb is True, user can remove selected items from the list', 'show_mb': True,},
            {'title': 'Checkable items', 'name': 'itemscheckable', 'type': 'itemselect',
             'value': dict(all_items=['item1', 'item2', 'item3'], selected=['item2']),
             'tip': 'If checkbox is True, user can select item by checking/unchecking items. Remove items is still used with standard selections',
             'show_pb': True, 'checkbox': True, 'show_mb': True,},
            {'title': 'Dragable items', 'name': 'itemsdragablecheckable', 'type': 'itemselect',
             'value': dict(all_items=['item1', 'item2', 'item3'], selected=['item2']),
             'tip': 'If dragdrop is True, user can drag or drop items inside the list', 'checkbox': True, 'dragdrop': True}, 
        ]},  
        {'title': 'Plain text:', 'name': 'texts', 'type': 'group', 'children': [
            {'title': 'Standard str', 'name': 'atte', 'type': 'str', 'value': 'this is a string you can edit'},
            {'title': 'Plain text', 'name': 'text', 'type': 'text', 'value': 'this is some text'},
            create_text_with_pattern_parameter(),
            {'title': 'Plain text', 'name': 'textpb', 'type': 'text_pb', 'value': 'this is some text',
             'tip': 'If text_pb type is used, user can add text to the parameter'},
        ]},

        {'title': 'Tables:', 'name': 'tables', 'type': 'group', 'children': [
            {'title': 'Table widget', 'name': 'tablewidget', 'type': 'table', 'value':
                OrderedDict(key1='data1', key2=24), 'header': ['keys', 'limits'], 'height': 100},
            {'title': 'Table view', 'name': 'tabular_table', 'type': 'table_view',
             'delegate': table.SpinBoxDelegate, 'menu': True,
             'value': table.TableModel([[0.1, 0.2, 0.3]], ['value1', 'value2', 'value3']),
             'tip': 'The advantage of the Table model lies in its modularity.\n For concrete examples see the'
                    'TableModelTabular and the TableModelSequential custom models in the'
                    ' pymodaq.utils.scanner module'},
        ]},  # The advantage of the Table model lies in its modularity for concrete examples see the
        # TableModelTabular and the TableModelSequential custom models in the pymodaq.utils.scanner module
    ]

    def __init__(self, tree=None):
        super().__init__(tree=tree)

    def value_changed(self, param):
        """
        """
        print(f'The parameter {param.name()} changed its value to {param.value()}')

        if param.name() == 'afloat':
            limits = (param.value(),
                      self.settings.child('numbers', 'linearslidefloatlimits').opts['limits'][1])
            self.settings.child('numbers', 'linearslidefloatlimits').setLimits(limits)
            self.settings.child('numbers', 'linearslidefloat').setOpts(min=limits[0])
        elif param.name() == 'anotherfloat':
            limits = (self.settings.child('numbers', 'linearslidefloatlimits').opts['limits'][0],
                      param.value())
            self.settings.child('numbers', 'linearslidefloatlimits').setLimits(limits) #either like this: preferred
            self.settings.child('numbers', 'linearslidefloat').setOpts(bounds=limits) # or like this!

    def options_changed(self, param, data: dict):
        if data.get("visible", None) is None:
            print(f'{param} option has been changed: {data}')

    def limits_changed(self, param, data):
        print(f'{param} limits have been changed: {data}')


def main():
    from pymodaq_gui.qt_utils import mkQApp

    app = mkQApp('Parameters')

    ptree = ParameterEx()
    ptree.settings_tree.show()
    # action_led: button fires sigActivated, which here sets the LED green then resets after 1 s
    def _on_action_led(param):
        param.setValue(True)
        QtCore.QTimer.singleShot(1000, lambda: param.setValue(False))
    ptree.settings.child('booleans', 'anactionled').sigActivated.connect(_on_action_led)

    ptree.settings.child('itemss', 'itemsbis').setValue(dict(all_items=['item1', 'item2', 'item3'],
                                                             selected=['item3']))

    ptree.settings.child('itemss', 'itemsbis').setValue(dict(all_items=['item1', 'item2', 'item3'],
                                                             selected=['item1', 'item3']))

    sys.exit(app.exec())


def main_expose():
    """Demonstrate the capability expose mode.

    Open the ctrl button (gear icon) on any *numeric* parameter (float, int,
    slide) to see the "Set as DAQ Move" / "Set as DAQ Viewer" submenu.
    Non-numeric parameters are excluded by the default capability filter.

    After selecting a role the parameter gains a joystick (move) or videocam
    (viewer) icon in column 0.  Opening the ctrl button on an already-bound
    parameter shows a checkmark next to the active role; selecting it again
    clears the binding.
    """
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq_gui.parameter import ParameterTree

    app = mkQApp('Parameter expose-mode demo')

    # ── build the ParameterEx UI, injecting our ParameterTree ────────────
    expose_tree = ParameterTree()
    ptree = ParameterEx(tree=expose_tree)
    tree = ptree.tree   # same object as expose_tree


    # ── per-parameter binding state ──────────────────────────────────────
    _current_roles: dict = {}   # param name → role key

    def _on_expose_requested(param, role: str) -> None:
        """Toggle binding: selecting the active role clears it."""
        name = param.name()
        if _current_roles.get(name) == role:
            _current_roles.pop(name)
            tree.set_param_role(param, None)
            print(f'[expose] cleared binding for "{name}"')
        else:
            _current_roles[name] = role
            tree.set_param_role(param, role)
            print(f'[expose] "{name}" → {role}')

    tree.expose_requested.connect(_on_expose_requested)

    # ── pre-bind a couple of params so icons are visible on startup ──────
    _on_expose_requested(ptree.settings.child('numbers', 'afloat'), 'move')
    _on_expose_requested(ptree.settings.child('numbers', 'anotherfloat'), 'viewer')

    ptree.settings_tree.show()
    sys.exit(app.exec())


def main_icons():
    """Demonstrate dynamic column-0 icons and custom context actions.

    * The ``afloat`` parameter starts with a ``gear2`` icon set via its
      ``context`` opt (handled by the gear button menu).
    * Selecting "Mark as done" emits ``param.sigContextMenu`` and sets a
      ``check`` icon via ``param.setOpts(icon=...)``.
    * ``anotherfloat`` has no initial icon; its icon is set programmatically
      via ``tree.set_param_icon`` after the tree is built.
    * Selecting "Clear icon" on either param clears its icon.
    """
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq_gui.parameter import ParameterTree

    app = mkQApp('Parameter icon demo')

    # A minimal parameter set focusing on icon features
    params = [
        {'title': 'Numbers:', 'name': 'numbers', 'type': 'group', 'children': [
            {'title': 'Float with context actions', 'name': 'afloat',
             'type': 'float', 'value': 1.0, 'min': 0.,
             'icon': 'gear2',   # initial display icon via opt
             'context': {'mark': 'Mark as done', 'clear': 'Clear icon'},
             'tip': 'Gear button shows "Mark as done" / "Clear icon"'},
            {'title': 'Float set via set_param_icon', 'name': 'anotherfloat',
             'type': 'float', 'value': 2.0, 'min': 0.,
             'context': {'clear': 'Clear icon'},
             'tip': 'Icon is set programmatically after tree construction'},
        ]},
    ]

    from pymodaq_gui.managers.parameter_manager import ParameterManager

    class IconDemo(ParameterManager):
        params = params

        def value_changed(self, param):
            pass

    ptree = IconDemo(tree=ParameterTree())
    tree = ptree.tree

    # Set icon programmatically (no 'icon' opt on this param)
    tree.set_param_icon(ptree.settings.child('numbers', 'anotherfloat'), 'led')

    def _on_context(param, action):
        if action == 'mark':
            param.setOpts(icon='check')   # dynamic update via opt
            print(f'[icon demo] {param.name()} marked — icon changed to check')
        elif action == 'clear':
            param.setOpts(icon=None)      # clear
            print(f'[icon demo] {param.name()} icon cleared')

    ptree.settings.sigContextMenu.connect(_on_context)

    ptree.settings_tree.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--expose', action='store_true',
                        help='Run the expose-mode demo instead of the standard one')
    parser.add_argument('--icons', action='store_true',
                        help='Run the dynamic-icon / context-actions demo')
    args = parser.parse_args()
    if args.expose:
        main_expose()
    elif args.icons:
        main_icons()
    else:
        main()
