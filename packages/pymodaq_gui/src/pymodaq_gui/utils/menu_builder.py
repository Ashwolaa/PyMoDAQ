"""Utility for building nested QMenu structures from iterables"""

from qtpy import QtWidgets
from typing import Callable, Tuple


class NestedMenuBuilder:
    """Builds nested QMenu structures from dict/list/tuple iterables.

    This class provides reusable logic for creating hierarchical menus
    from nested data structures.

    Parameters
    ----------
    menu : QMenu
        The root menu to populate
    on_item_selected : Callable[[Tuple], None]
        Callback function called when a leaf item is selected.
        Receives the path tuple as argument.
    """

    def __init__(self, menu: QtWidgets.QMenu, on_item_selected: Callable[[Tuple], None]):
        self.menu = menu
        self.on_item_selected = on_item_selected

    def build(self, items, path: Tuple = ()):
        """Build the menu structure from an iterable.

        Parameters
        ----------
        items : dict, list, or tuple
            Nested structure defining the menu hierarchy.
            - dict: keys become menu items, values define children
            - list/tuple of str: items become leaf actions
            - list/tuple of dict: each dict is processed as above
        path : tuple
            Current path in the hierarchy (used for callbacks)
        """
        self._build_menu_from_iterable(self.menu, items, path)

    def _build_menu_from_iterable(self, menu: QtWidgets.QMenu, items, path: Tuple):
        """Recursively build menu from iterable structure."""
        if isinstance(items, dict):
            for key, value in items.items():
                self._handle_menu_item(menu, key, value, path)
        elif isinstance(items, (list, tuple)):
            for item in items:
                if isinstance(item, dict):
                    for key, value in item.items():
                        self._handle_menu_item(menu, key, value, path)
                elif isinstance(item, str):
                    self._add_leaf_action(menu, item, path + (item,))

    def _handle_menu_item(self, menu: QtWidgets.QMenu, key, value, path: Tuple):
        """Handle a single menu item (key-value pair)."""
        new_path = path + (key,)

        if self._is_nested(value):
            # Create submenu and recurse
            submenu = menu.addMenu(key)
            self._build_menu_from_iterable(submenu, value, new_path)
        else:
            # Create leaf action
            self._add_leaf_action(menu, key, new_path)

    @staticmethod
    def _is_nested(value) -> bool:
        """Check if a value represents nested structure."""
        return isinstance(value, (dict, list, tuple)) and value  # Not empty

    def _add_leaf_action(self, menu: QtWidgets.QMenu, name: str, path: Tuple):
        """Add a leaf action to the menu."""
        action = menu.addAction(name)
        action.triggered.connect(lambda checked, data=path: self.on_item_selected(data))


def build_nested_menu(menu: QtWidgets.QMenu, items, on_item_selected: Callable[[Tuple], None]):
    """Convenience function to build a nested menu.

    Parameters
    ----------
    menu : QMenu
        The menu to populate
    items : dict, list, or tuple
        Nested structure defining the menu hierarchy
    on_item_selected : Callable[[Tuple], None]
        Callback when a leaf item is selected
    """
    builder = NestedMenuBuilder(menu, on_item_selected)
    builder.build(items)
