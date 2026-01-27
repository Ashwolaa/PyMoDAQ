from qtpy.QtCore import Signal

from pymodaq.control_modules.daq_types import SelectedActuator
from pymodaq.control_modules.control_module_selector import ModuleSelector, categorize_items


def get_actuator_menu_entries():
    """Lazy import of ACTUATOR_NAMES to avoid import-time errors"""
    try:
        from pymodaq.control_modules.instruments import ACTUATOR_NAMES
        return ACTUATOR_NAMES
    except Exception:
        return []


class ActuatorSelector(ModuleSelector):
    """Selector widget for actuator modules using categorized menu

    Extends ModuleSelector to provide Mock/Plugin/Remote categorization
    for actuator selection.
    """

    module_changed = Signal(SelectedActuator)

    def __init__(self, add_menu_entries: dict = None):
        actuator_names = get_actuator_menu_entries()
        if add_menu_entries is None:
            add_menu_entries = categorize_items(actuator_names) if actuator_names else {'Plugin': ['Mock']}

        default_actuator = SelectedActuator(actuator_names[0] if actuator_names else 'Mock')
        super().__init__(str(default_actuator), add_menu_entries)

        self._selected_module: SelectedActuator = default_actuator

    @property
    def selected_module(self) -> SelectedActuator:
        return self._selected_module

    @selected_module.setter
    def selected_module(self, value: SelectedActuator):
        self._selected_module = value
        self.add_widget.setText(str(value))
        self.module_changed.emit(value)

    def _add_menu_item_selected(self, path_tuple):
        """Called when a menu item is selected from the nested add menu"""
        # For actuators, the last element is the actuator name
        actuator_name = path_tuple[-1]
        self.add_widget.setText(actuator_name)
        self.add_widget.adjustSize()
        self._selected_module = SelectedActuator(actuator_name)
        self.module_changed.emit(self._selected_module)


if __name__ == '__main__':
    import sys
    from pymodaq_gui.qt_utils import mkQApp

    app = mkQApp('ActuatorSelector')

    selector = ActuatorSelector()
    selector.add_widget.show()

    def on_changed(sel: SelectedActuator):
        print(f"Selected: {sel}")

    selector.module_changed.connect(on_changed)

    sys.exit(app.exec())
