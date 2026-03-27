from qtpy import QtWidgets, QtCore

class ComboBox(QtWidgets.QComboBox):

    items_changed = QtCore.Signal(list)
    enabled_changed = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

    def get_items(self) -> list[str]:
        return [self.itemText(index) for index in range(self.count())]

    def set_items(self, items: list[str], item_selected: str = None):
        self.clear()
        self.addItems(items)
        self.items_changed.emit(items)
        if item_selected is not None:
            self.setCurrentText(item_selected)
    items = QtCore.Property(list, get_items, set_items, notify=items_changed)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.enabled_changed.emit(enabled)