# -*- coding: utf-8 -*-
"""
Created the 31/08/2023

@author: Sebastien Weber
"""
import numpy as np
import pytest
from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun, main,
                                                          DataActuatorType, check_units,
                                                          DataActuator, comon_parameters)
from pymodaq.control_modules.utils import create_controller_param


def test_check_units():

    dwa = DataActuator('myact', data=24., units='km')

    assert check_units(dwa, 'm') == dwa


@pytest.mark.parametrize("ISMULTI, AXIS_NAMES, EPSILON, UNITS",
                         [(True, ['a', 'b', 'c'], 0.1, 'mm'),
                          (False, ['a', 'c'], 0.1, 'mm'),
                          (False, [], 0.001, 'mm'),
                          ])
def test_axis_list_legacy(qtbot, ISMULTI, AXIS_NAMES, EPSILON, UNITS):


    class HardwareWithList(DAQ_Move_base):
        _controller_units = UNITS
        # find available COM ports

        is_multiaxes = ISMULTI
        axes_names = AXIS_NAMES.copy()
        _epsilon = EPSILON

        params = comon_parameters_fun(is_multiaxes, axes_names, epsilon=_epsilon)

    hardware = HardwareWithList()

    for ind, axis_name in enumerate(AXIS_NAMES):
        hardware.axis_name = axis_name

        assert hardware.axis_index_key == ind

        assert hardware.axis_names == AXIS_NAMES
        assert hardware.axis_name == axis_name
        assert hardware.axis_value == axis_name

        assert hardware.epsilon == pytest.approx(EPSILON)
        assert np.allclose(hardware.epsilons, [EPSILON for _ in range(len(AXIS_NAMES))])

        assert hardware.axis_unit == UNITS
        assert hardware.axis_units == [UNITS for _ in range(len(AXIS_NAMES))]



@pytest.mark.parametrize("AXIS_NAMES, EPSILONS, UNITS, error",
                         [(['a', 'b', 'c'], 0.1, 'mm', False),
                          (['a', 'b',], [0.1, 0.65], 'mm', False),
                          (['a', 'c'], 0.1, ['mm', '°'], False),
                          (['a', 'c'], [0.1, 0.001], ['mm', '°'], False),
                          (['a', 'b', 'c'], 0.1, ['mm', '°'], True),
                          (['a', 'c'], [0.1], ['mm', '°'], True),
                          (['a', 'b', 'c'], [0.1, 0.001], ['mm', '°', 's'], True),
                          ])
def test_axis_list(qtbot, AXIS_NAMES, EPSILONS, UNITS, error):

    class HardwareWithList(DAQ_Move_base):
        _axis_names = AXIS_NAMES
        _controller_units = UNITS
        _epsilons = EPSILONS

        params = comon_parameters_fun(axis_names=_axis_names)

    if error:
        with pytest.raises(ValueError):
            hardware = HardwareWithList()
    else:
        hardware = HardwareWithList()

        for ind, axis_name in enumerate(AXIS_NAMES):
            hardware.axis_name = axis_name

            assert hardware.axis_index_key == ind

            assert hardware.axis_names == AXIS_NAMES
            assert hardware.axis_name == axis_name
            assert hardware.axis_value == axis_name

            if not isinstance(EPSILONS, list):
                assert hardware.epsilon == pytest.approx(EPSILONS)
                assert np.allclose(hardware.epsilons, [EPSILONS for _ in range(len(AXIS_NAMES))])
            else:
                assert hardware.epsilon == pytest.approx(EPSILONS[ind])
                assert np.allclose(hardware.epsilons, EPSILONS)

            if not isinstance(UNITS, list):
                assert hardware.axis_unit == UNITS
                assert hardware.axis_units == [UNITS for _ in range(len(AXIS_NAMES))]
            else:
                assert hardware.axis_unit == UNITS[ind]
                assert hardware.axis_units == UNITS


@pytest.mark.parametrize("AXIS_NAMES, EPSILONS, UNITS, error",
                         [({'a': 0, 'b': 2, 'c': 5}, 0.1, 'mm', None),
                          ({'a': 0, 'b': 2}, [0.1, 0.65], 'mm', TypeError),
                          ({'a': 0, 'b': 2}, {'a': 0.1, 'b': 0.65}, 'mm', None),
                          ({'a': 0, 'b': 2}, 0.1, {'a': 'mm', 'b': '°'}, None),
                          ({'a': 0, 'b': 2}, {'a': 0.1, 'b': 0.65}, {'a': 'mm', 'b': '°'}, None),
                          ({'a': 0, 'b': 2}, {'a': 0.1,}, {'a': 'mm', 'b': '°'}, ValueError),
                          ({'a': 0, 'b': 2}, {'a': 0.1, 'b': 0.65}, {'b': '°'}, ValueError),
                          ])
def test_axis_dict(qtbot, AXIS_NAMES, EPSILONS, UNITS, error):

    class HardwareWithList(DAQ_Move_base):
        _axis_names = AXIS_NAMES
        _controller_units = UNITS
        _epsilons = EPSILONS

        params = comon_parameters_fun(axis_names=_axis_names)

    if error is not None:
        with pytest.raises(error):
            hardware = HardwareWithList()
    else:
        hardware = HardwareWithList()

        for axis_name, axis_value in AXIS_NAMES.items():
            hardware.axis_name = axis_name

            assert hardware.axis_index_key == axis_name

            assert hardware.axis_names == AXIS_NAMES
            assert hardware.axis_name == axis_name
            assert hardware.axis_value == axis_value

            if not isinstance(EPSILONS, dict):
                assert hardware.epsilon == pytest.approx(EPSILONS)
                assert np.allclose(list(hardware.epsilons.values()),
                                   [EPSILONS for _ in range(len(AXIS_NAMES))])
            else:
                assert hardware.epsilon == pytest.approx(EPSILONS[axis_name])
                assert hardware.epsilons == EPSILONS

            if not isinstance(UNITS, dict):
                assert hardware.axis_unit == UNITS
                assert list(hardware.axis_units.values()) == [UNITS for _ in range(len(AXIS_NAMES))]
            else:
                assert hardware.axis_unit == UNITS[axis_name]
                assert hardware.axis_units == UNITS


class TestPerChannelPathShim:
    """DAQ_Move_base._per_channel_path detects old/new layout at runtime.

    There are three plugin layouts:

    1. **Truly old style** (legacy): axis in ``controller`` group, per-channel
       params (units, epsilon, …) at top level — no ``axis_settings`` group.
    2. **Single-axis new style**: flat ``axis_settings`` (axis selector with
       single empty-string limit, plus per-channel params directly).
    3. **Multi-axis new style**: ``axis_settings`` with per-axis sub-groups.

    ``comon_parameters_fun`` now generates layouts 2 or 3 depending on
    whether axis_names has more than one entry.
    """

    def _make_truly_old_style(self, axis_names=None):
        """Plugin using truly old layout: axis in controller, per-channel params flat."""
        from pymodaq_gui.parameter.ioxml import VALID_FOR_CONFIGURATION
        names = axis_names or ['X', 'Y']

        class TrulyOldPlugin(DAQ_Move_base):
            _axis_names = names
            params = [
                create_controller_param(names[0], names.copy()),  # axis inside controller
                *comon_parameters(),  # flat per-channel at top level
            ]

        return TrulyOldPlugin()

    def _make_single_axis_style(self, axis_names=None):
        """Plugin with single-axis flat axis_settings (new-style, single axis)."""
        names = axis_names or ['X']

        class SingleAxisPlugin(DAQ_Move_base):
            _axis_names = names
            params = comon_parameters_fun(axis_names=names)

        return SingleAxisPlugin()

    def _make_multiaxis_style(self, axis_names=None):
        """Plugin with per-axis sub-groups inside axis_settings (new-style, multi-axis)."""
        names = axis_names or ['X', 'Y']

        class MultiAxisPlugin(DAQ_Move_base):
            _axis_names = names
            params = comon_parameters_fun(axis_names=names)

        return MultiAxisPlugin()

    # --- Truly old style (axis in controller, no axis_settings) ---

    def test_old_style_axis_path(self, qtbot):
        hw = self._make_truly_old_style()
        assert hw._per_channel_path('axis') == ('controller', 'axis')

    def test_old_style_units_path(self, qtbot):
        hw = self._make_truly_old_style()
        assert hw._per_channel_path('units') == ('units',)

    def test_old_style_bounds_path(self, qtbot):
        hw = self._make_truly_old_style()
        assert hw._per_channel_path('bounds', 'is_bounds') == ('bounds', 'is_bounds')

    def test_old_style_axis_name_readable(self, qtbot):
        hw = self._make_truly_old_style(['X', 'Y'])
        assert hw.axis_name in ['X', 'Y']

    def test_old_style_axis_name_settable(self, qtbot):
        hw = self._make_truly_old_style(['X', 'Y'])
        hw.axis_name = 'Y'
        assert hw.axis_name == 'Y'

    # --- Single-axis new style (flat axis_settings) ---

    def test_single_axis_axis_path(self, qtbot):
        hw = self._make_single_axis_style(['X'])
        assert hw._per_channel_path('axis') == ('axis_settings', 'axis')

    def test_single_axis_units_path(self, qtbot):
        hw = self._make_single_axis_style(['X'])
        # Single-axis: no per-axis sub-group, units directly in axis_settings
        assert hw._per_channel_path('units') == ('axis_settings', 'units')

    def test_single_axis_bounds_path(self, qtbot):
        hw = self._make_single_axis_style(['X'])
        assert hw._per_channel_path('bounds', 'is_bounds') == ('axis_settings', 'bounds', 'is_bounds')

    def test_single_axis_name_readable(self, qtbot):
        hw = self._make_single_axis_style(['X'])
        assert hw.axis_name == ''  # single-axis sentinel

    # --- Multi-axis new style (per-axis sub-groups) ---

    def test_new_style_axis_path(self, qtbot):
        hw = self._make_multiaxis_style()
        assert hw._per_channel_path('axis') == ('axis_settings', 'axis')

    def test_new_style_units_path(self, qtbot):
        hw = self._make_multiaxis_style(['X', 'Y'])
        # Multi-axis: per-axis sub-groups; units routed through the active axis (default 'X')
        assert hw._per_channel_path('units') == ('axis_settings', 'X', 'units')

    def test_new_style_bounds_path(self, qtbot):
        hw = self._make_multiaxis_style(['X', 'Y'])
        # Multi-axis: bounds routed through active axis sub-group
        assert hw._per_channel_path('bounds', 'is_bounds') == ('axis_settings', 'X', 'bounds', 'is_bounds')

    def test_new_style_axis_name_readable(self, qtbot):
        hw = self._make_multiaxis_style(['X', 'Y'])
        assert hw.axis_name in ['X', 'Y']

    def test_new_style_axis_name_settable(self, qtbot):
        hw = self._make_multiaxis_style(['X', 'Y'])
        hw.axis_name = 'Y'
        assert hw.axis_name == 'Y'

    def test_new_style_units_path_after_axis_change(self, qtbot):
        hw = self._make_multiaxis_style(['X', 'Y'])
        hw.axis_name = 'Y'
        # After switching to 'Y', units are routed through the 'Y' sub-group
        assert hw._per_channel_path('units') == ('axis_settings', 'Y', 'units')
