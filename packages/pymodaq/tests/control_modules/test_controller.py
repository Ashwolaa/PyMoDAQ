"""Tests for Controller: the GUI-side handle to a device, over a real hardware thread."""
from __future__ import annotations

import threading

import numpy as np
import pytest

from pymodaq.control_modules.capabilities import control, measurement
from pymodaq.control_modules.controller import Controller, controller_class
from pymodaq.control_modules.hardware_registry import HardwareKey, HardwareRegistry


class _Reading:
    def __init__(self, names):
        self._arrays = {name: np.arange(4.0) + 1 for name in names}

    def get_data_from_name(self, name):
        return self._arrays[name]


class Spectrometer:
    params: list = []
    spectrum = measurement(units='counts', shape=(4,))
    exposure = control(units='ms', lo=1, hi=1000, epsilon=0.1)

    def __init__(self):
        self.written = []

    def open(self, settings):
        pass

    def close(self):
        pass

    def read(self, names=None, fresh=True):
        return _Reading(names)

    def write(self, name, value):
        self.written.append((name, value))


@pytest.fixture
def registry():
    registry = HardwareRegistry()
    yield registry
    registry.close_all()


def attach(registry, controller_id=0):
    key = HardwareKey(hardware_class=Spectrometer, controller_id=controller_id)
    return key, registry.attach(key, Spectrometer)


class TestGeneratedProperties:

    def test_one_property_per_declared_quantity(self):
        cls = controller_class(Spectrometer)
        assert issubclass(cls, Controller)
        assert isinstance(getattr(cls, 'spectrum'), property)
        assert isinstance(getattr(cls, 'exposure'), property)

    def test_measurement_property_has_no_setter(self):
        assert controller_class(Spectrometer).spectrum.fset is None

    def test_control_property_has_a_setter(self):
        assert controller_class(Spectrometer).exposure.fset is not None


class TestDeviceState:

    def test_connected_follows_the_device_status(self, registry, qtbot):
        key, ctrl = attach(registry)
        assert ctrl.connected is False
        ctrl.thread.ini_hardware()
        assert ctrl.connected is True
        ctrl.thread.close_hardware()
        assert ctrl.connected is False

    def test_controller_is_created_before_the_device_is_initialised(self, registry):
        key, ctrl = attach(registry)
        assert isinstance(ctrl, Controller)
        assert ctrl.capabilities.controls[0].name == 'exposure'


class TestWrite:

    def test_setting_a_control_writes_it_on_the_device(self, registry, qtbot):
        key, ctrl = attach(registry)
        ctrl.thread.ini_hardware()
        plugin = ctrl.thread._plugin
        ctrl.exposure = 20.0
        qtbot.waitUntil(lambda: plugin.written == [('exposure', 20.0)], timeout=2000)


class TestPoll:

    def test_polled_measurement_updates_its_property(self, registry, qtbot):
        key, ctrl = attach(registry)
        ctrl.thread.ini_hardware()
        assert ctrl.spectrum is None
        ctrl.poll('spectrum', 20.0)
        qtbot.waitUntil(lambda: ctrl.spectrum is not None, timeout=2000)
        assert list(ctrl.spectrum) == [1.0, 2.0, 3.0, 4.0]

    def test_poll_before_open_raises(self, registry):
        key, ctrl = attach(registry)
        with pytest.raises(RuntimeError, match='not open'):
            ctrl.poll('spectrum', 20.0)

    def test_read_before_open_raises(self, registry):
        key, ctrl = attach(registry)
        with pytest.raises(RuntimeError, match='not open'):
            ctrl.read('spectrum', lambda data: None)

    def test_polls_are_cleared_when_the_device_closes(self, registry, qtbot):
        key, ctrl = attach(registry)
        ctrl.thread.ini_hardware()
        ctrl.poll('spectrum', 20.0)
        ctrl.thread.close_hardware()
        assert ctrl._polled == {}
        ctrl.thread.ini_hardware()
        assert ctrl.poll('spectrum', 20.0) is not None

    def test_polling_again_with_the_same_period_returns_the_same_subscription(self, registry):
        key, ctrl = attach(registry)
        ctrl.thread.ini_hardware()
        assert ctrl.poll('spectrum', 20.0) is ctrl.poll('spectrum', 20.0)

    def test_polling_again_with_another_period_raises(self, registry):
        key, ctrl = attach(registry)
        ctrl.thread.ini_hardware()
        ctrl.poll('spectrum', 20.0)
        with pytest.raises(ValueError, match='already polled'):
            ctrl.poll('spectrum', 50.0)

    def test_stop_poll_keeps_the_last_value(self, registry, qtbot):
        key, ctrl = attach(registry)
        ctrl.thread.ini_hardware()
        ctrl.poll('spectrum', 20.0)
        qtbot.waitUntil(lambda: ctrl.spectrum is not None, timeout=2000)
        ctrl.stop_poll('spectrum')
        last = ctrl.spectrum
        qtbot.wait(100)
        assert ctrl.spectrum is last
        assert 'spectrum' not in ctrl._polled

    def test_stop_poll_of_an_unpolled_name_is_a_noop(self, registry):
        key, ctrl = attach(registry)
        ctrl.stop_poll('spectrum')


class TestBlockingRead:

    def test_script_thread_gets_the_reading(self, registry, qtbot):
        key, ctrl = attach(registry)
        ctrl.thread.ini_hardware()
        result = {}

        def script():
            result['value'] = ctrl.read_blocking('spectrum', timeout=3)

        worker = threading.Thread(target=script)
        worker.start()
        qtbot.waitUntil(lambda: not worker.is_alive(), timeout=5000)
        assert list(result['value']) == [1.0, 2.0, 3.0, 4.0]

    def test_fails_at_once_when_the_device_is_not_open(self, registry):
        key, ctrl = attach(registry)
        with pytest.raises(RuntimeError, match='not open'):
            ctrl.read_blocking('spectrum')
