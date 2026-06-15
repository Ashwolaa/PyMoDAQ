"""Integration test: one new-style plugin declaring mixed ``Capabilities``
(one ``Observable`` detector channel + one ``ContinuousVariable`` axis),
driven end-to-end through ``ControllerThread``.

This validates that the ``capabilities.py`` dataclasses are sufficient to
describe a real multi-channel instrument, and that ControllerThread's
existing new-style dispatch (``query_data`` / ``change_to`` /
``capabilities_signal``) works against such a plugin.
"""
from __future__ import annotations

import numpy as np

from pymodaq.control_modules.controller_thread import ControllerThread
from pymodaq.control_modules.capabilities import (
    Capabilities, ContinuousVariable, Observable,
)
from pymodaq.utils.data import DataActuator, DataFromPlugins, DataToExport


SPECTRUM_SHAPE = (16,)


class MockSpectrometerWithAxis:
    """New-style plugin: one 'position' axis (Variable) + one 'spectrum'
    detector channel (Observable). The spectrum baseline tracks the axis
    position so a write-then-snap round trip is observable.
    """

    params: list = []

    capabilities = Capabilities(
        observables=[Observable(name='spectrum', label='Spectrum', units='counts',
                                 dtype='float64', shape=SPECTRUM_SHAPE)],
        variables=[ContinuousVariable(name='position', label='Position', units='mm',
                                       lo=0.0, hi=10.0, epsilon=0.01)],
    )

    def __init__(self):
        self._position = 0.0
        self.open_called_with = None
        self.query_calls: list = []
        self.change_calls: list = []

    def open(self, settings) -> None:
        self.open_called_with = settings

    def close(self) -> None:
        pass

    def query_data(self, names=None, fresh=True):
        names = list(names) if names else ['spectrum', 'position']
        self.query_calls.append(names)
        dte = DataToExport('mock_spectrometer')
        for name in names:
            if name == 'spectrum':
                data = np.arange(SPECTRUM_SHAPE[0], dtype='float64') + self._position
                dte.append(DataFromPlugins(name='spectrum', data=[data]))
            elif name == 'position':
                dte.append(DataActuator('position', data=[np.array([self._position])]))
        return dte

    def change_to(self, name, value) -> None:
        self.change_calls.append((name, value))
        if name == 'position':
            self._position = float(value)

    def commit_settings(self, param) -> None:
        pass


class Collector:
    """Accumulate Qt signal emissions for assertions."""

    def __init__(self):
        self.calls: list = []

    def __call__(self, *args):
        self.calls.append(args)

    @property
    def count(self) -> int:
        return len(self.calls)

    def last(self):
        return self.calls[-1] if self.calls else None


def make_thread() -> ControllerThread:
    return ControllerThread(plugin_class=MockSpectrometerWithAxis, params_state=None)


class TestMixedCapabilitiesNewStylePlugin:

    def test_capabilities_signal_emits_declared_capabilities(self, qapp):
        thread_obj = make_thread()
        collector = Collector()
        thread_obj.capabilities_signal.connect(collector)
        thread_obj.ini_hardware()

        assert collector.count == 1
        caps: Capabilities = collector.last()[0]
        assert caps is MockSpectrometerWithAxis.capabilities
        assert [o.name for o in caps.observables] == ['spectrum']
        assert caps.observables[0].shape == SPECTRUM_SHAPE
        assert [v.name for v in caps.variables] == ['position']
        assert caps.variables[0].lo == 0.0
        assert caps.variables[0].hi == 10.0
        assert caps.variables[0].epsilon == 0.01

    def test_snap_observable_channel_returns_declared_shape(self, qapp):
        thread_obj = make_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)

        thread_obj.request_snap('spectrum', Naverage=1)

        assert collector.count == 1
        channel, dte, is_temp = collector.last()
        assert channel == 'spectrum'
        assert is_temp is False
        spectrum = dte.get_data_from_name('spectrum')
        assert spectrum.data[0].shape == SPECTRUM_SHAPE

    def test_write_then_read_variable_channel_round_trips(self, qapp):
        thread_obj = make_thread()
        thread_obj.ini_hardware()
        change_collector = Collector()
        read_collector = Collector()
        thread_obj.change_done.connect(change_collector)
        thread_obj.data_ready.connect(read_collector)

        thread_obj.request_write('position', 5.0)
        assert change_collector.count == 1
        assert change_collector.last() == ('position', 5.0)

        thread_obj.request_read('position')
        channel, dte, _ = read_collector.last()
        assert channel == 'position'
        position = dte.get_data_from_name('position')
        assert position.data[0][0] == 5.0

    def test_write_to_position_shifts_spectrum_baseline(self, qapp):
        thread_obj = make_thread()
        thread_obj.ini_hardware()
        thread_obj.request_write('position', 2.0)

        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_snap('spectrum', Naverage=1)

        _, dte, _ = collector.last()
        spectrum = dte.get_data_from_name('spectrum')
        assert spectrum.data[0][0] == 2.0
