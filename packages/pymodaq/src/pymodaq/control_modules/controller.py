"""GUI-side handle to one device.

A :class:`Controller` is created by the registry for each device. It talks to the device's
:class:`~pymodaq.control_modules.hardware_thread.HardwareThread` through signals only, so the
plugin is only ever called on the hardware thread. Each declared measurement or control becomes a
property: a control's setter queues a write, and a getter returns the latest value received.
"""
from __future__ import annotations

import functools
import threading

from qtpy.QtCore import QObject, Qt, Signal

from pymodaq.control_modules.capabilities import Access, Capabilities, Quantity
from pymodaq.control_modules.subscription import Subscription

__all__ = ['Controller', 'controller_class']


def _quantity_property(quantity: Quantity) -> property:
    name = quantity.name

    def getter(self: Controller):
        return self._last_values.get(name)

    if quantity.access is Access.CONTROL:
        def setter(self: Controller, value):
            self.write_requested.emit(name, value)

        return property(getter, setter, doc=quantity.docs)
    return property(getter, doc=quantity.docs)


class Controller(QObject):
    """One per device. Created by the registry, before the device is initialised.

    The controller must exist before ``ini_hardware`` runs, so that it receives the status
    that announces the device is open.
    """

    write_requested = Signal(str, object)      # → thread.request_write
    subscribe_requested = Signal(object)       # → thread.subscribe
    unsubscribe_requested = Signal(object)     # → thread.unsubscribe
    status = Signal(bool, str)                 # ← thread.hardware_status
    error = Signal(str)                        # ← thread.error: an operation failed, the device is still open

    def __init__(self, thread, settings, capabilities: Capabilities, parent: QObject | None = None):
        super().__init__(parent)
        self.capabilities = capabilities
        self.settings = settings
        self.thread = thread
        self._connected = False
        self._last_values: dict[str, object] = {}
        self._polled: dict[str, Subscription] = {}
        self.write_requested.connect(thread.request_write)
        self.subscribe_requested.connect(thread.subscribe)
        self.unsubscribe_requested.connect(thread.unsubscribe)
        thread.hardware_status.connect(self._on_status)
        thread.error.connect(self.error)
        thread.capabilities_signal.connect(self._on_instance_capabilities)

    @property
    def connected(self) -> bool:
        return self._connected

    def _on_instance_capabilities(self, capabilities: Capabilities) -> None:
        """Keep the capabilities the plugin reported after open, for introspection. Attributes stay class-level."""
        self.capabilities = capabilities

    def _on_status(self, connected: bool, info: str) -> None:
        self._connected = connected
        if not connected:
            self._polled.clear()  # the thread released these subscriptions when it closed the device
        self.status.emit(connected, info)

    def _require_open(self, name: str) -> None:
        if not self._connected:
            raise RuntimeError(f'cannot access {name!r}: the device is not open')

    def poll(self, name: str, period_ms: float) -> Subscription:
        """Read *name* every *period_ms* so that its property stays up to date.

        Only the newest value matters, so the subscription uses the 'latest' policy.
        Polling a name again returns the same subscription; a different period raises.
        Raises RuntimeError if the device is not open.
        """
        self._require_open(name)
        if name in self._polled:
            existing = self._polled[name]
            if existing.period_ms != period_ms:
                raise ValueError(f'{name!r} is already polled every {existing.period_ms} ms')
            return existing
        sub = Subscription(name, period_ms, policy='latest')
        sub.data_ready.connect(lambda data, is_temp, t: self._on_reading(name, data, sub))
        self._polled[name] = sub
        self.subscribe_requested.emit(sub)
        return sub

    def stop_poll(self, name: str) -> None:
        """Stop polling *name*. Its property keeps the last value received."""
        sub = self._polled.pop(name, None)
        if sub is not None:
            self.unsubscribe_requested.emit(sub)

    def read(self, name: str, on_value) -> Subscription:
        """Read *name* once, asynchronously: *on_value(data)* is called when the reading arrives."""
        self._require_open(name)
        sub = Subscription(name, None)
        sub.data_ready.connect(lambda data, is_temp, t: (sub.acknowledge(), on_value(data)))
        self.subscribe_requested.emit(sub)
        return sub

    def read_blocking(self, name: str, timeout: float = 5.0):
        """Read *name* once and wait for the value. For scripts only: never call it from the hardware thread."""
        if self.thread.is_device_thread():
            raise RuntimeError('read_blocking would wait on the hardware thread that must answer it')
        self._require_open(name)
        done = threading.Event()
        result: dict[str, object] = {}

        def on_value(data):
            result['value'] = data
            done.set()

        # auto_delete=False: a script thread has no event loop to run a queued deletion.
        sub = Subscription(name, None, auto_delete=False)
        # Direct: the hardware thread calls on_value itself, so the script thread needs no event loop.
        sub.data_ready.connect(lambda data, is_temp, t: (sub.acknowledge(), on_value(data)), Qt.DirectConnection)
        self.subscribe_requested.emit(sub)
        if not done.wait(timeout):
            raise TimeoutError(f'no reading of {name!r} within {timeout} s')
        return result['value']

    def close(self) -> None:
        """Stop every poll."""
        for sub in self._polled.values():
            self.unsubscribe_requested.emit(sub)
        self._polled.clear()

    def _on_reading(self, name: str, data: object, sub: Subscription) -> None:
        self._last_values[name] = data
        sub.acknowledge()


@functools.lru_cache(maxsize=None)
def controller_class(device_cls: type) -> type:
    """A :class:`Controller` subclass with one property per quantity declared on *device_cls*.

    A quantity may not reuse the name of an existing :class:`Controller` attribute, since the
    property would replace it.
    """
    caps = Capabilities.from_device(device_cls)
    quantities = caps.measurements + caps.controls
    reserved = set(dir(Controller)) | {'capabilities', 'settings', 'thread'}
    taken = sorted(q.name for q in quantities if q.name in reserved)
    if taken:
        raise ValueError(f'{device_cls.__name__}: quantity names {taken} clash with Controller attributes')
    attrs = {q.name: _quantity_property(q) for q in quantities}
    return type(f'{device_cls.__name__}Controller', (Controller,), attrs)
