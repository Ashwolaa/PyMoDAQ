from qtpy import QtWidgets, QtCore
from qtpy.QtCore import QObject, Signal, Slot
from collections import OrderedDict


class DictProxy(QtCore.QObject):
    resized = Signal(dict)


class OrderedDictProxy(QtCore.QObject):
    resized = Signal(OrderedDict)    

class SignalDict(dict):
    def __init__(self, *args):
        super().__init__(*args)
        self._proxy = DictProxy()
        self.resized = self._proxy.resized

    def append(self, item):
        super().append(item)
        self.resized.emit(self)

    def extend(self, iterable):
        super().extend(iterable)
        self.resized.emit(self)

    def pop(self, *args):
        item = super().pop(*args)
        self.resized.emit(self)
        return item
    
    def remove(self, *args):
        item = super().remove(*args)
        self.resized.emit(self)
        return item

    # this is required for slicing -> myList[:] = []
    # you might want to check if the length of the list is actually changed
    # before emitting the signal
    def __setitem__(self, *args, **kwargs):
        super().__setitem__(*args, **kwargs)
        self.resized.emit(self)

    def __delitem__(self, *args, **kwargs):
        super().__delitem__(*args, **kwargs)
        self.resized.emit(self)

    # this is required for concatenation -> myList += iterable
    def __iadd__(self, *args, **kwargs):
        super().__iadd__(*args, **kwargs)
        self.resized.emit(self)
        return self
    

class SignalOrderedDict(OrderedDict):
    def __init__(self, *args):
        super().__init__(*args)
        self._proxy = OrderedDictProxy()
        self.resized = self._proxy.resized

    def append(self, item):
        super().append(item)
        self.resized.emit(self)

    def extend(self, iterable):
        super().extend(iterable)
        self.resized.emit(self)

    def pop(self, *args):
        item = super().pop(*args)
        self.resized.emit(self)
        return item
    
    def remove(self, *args):
        item = super().remove(*args)
        self.resized.emit(self)
        return item

    # this is required for slicing -> myList[:] = []
    # you might want to check if the length of the list is actually changed
    # before emitting the signal
    def __setitem__(self, *args, **kwargs):
        super().__setitem__(*args, **kwargs)
        self.resized.emit(self)

    def __delitem__(self, *args, **kwargs):
        super().__delitem__(*args, **kwargs)
        self.resized.emit(self)

    # this is required for concatenation -> myList += iterable
    def __iadd__(self, *args, **kwargs):
        super().__iadd__(*args, **kwargs)
        self.resized.emit(self)
        return self
        