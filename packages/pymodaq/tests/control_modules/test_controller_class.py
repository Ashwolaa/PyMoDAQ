import pytest

from pymodaq.control_modules.capabilities import control, measurement
from pymodaq.control_modules.controller import Controller, controller_class


def test_quantity_named_like_a_controller_attribute_is_rejected():
    class Clashing:
        read = measurement(units='V')

    with pytest.raises(ValueError, match="'read'"):
        controller_class(Clashing)


def test_quantity_named_like_an_instance_attribute_is_rejected():
    class Clashing:
        settings = control(units='V')

    with pytest.raises(ValueError, match="'settings'"):
        controller_class(Clashing)


def test_controller_class_is_cached_per_device_class():
    class Device:
        position = control(units='mm')

    assert controller_class(Device) is controller_class(Device)
    assert issubclass(controller_class(Device), Controller)
    assert isinstance(controller_class(Device).position, property)
