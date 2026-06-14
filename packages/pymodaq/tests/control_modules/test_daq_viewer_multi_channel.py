"""Integration tests: two real DAQ_Viewer instances attached to ONE shared
new-style plugin (open/query_data/change_to), each subscribing to a
different named data ``channel`` of that plugin.

This exercises the ``controller.channel`` selector
(``DAQ_Viewer._derive_channel`` / ``channel_name`` / ``channel_names``):
each viewer's ``_channel`` is derived from its own local
``detector_settings -> controller -> channel`` value, and the CT-level
channel filter in ``DAQ_Viewer._on_ct_data_ready`` ensures a
``query_data(names=['ChannelA'])`` snap only reaches the viewer subscribed
to ``'ChannelA'``.

Modeled on ``test_daq_move_viewer_shared_ct.py``.
"""
from __future__ import annotations

import copy

import numpy as np
import pytest

from pymodaq_gui.parameter import Parameter

from pymodaq.control_modules.daq_viewer import DAQ_Viewer
from pymodaq.control_modules.controller_registry import ControllerRegistry
from pymodaq.control_modules.utils import create_controller_param
from pymodaq.utils.data import DataFromPlugins, DataToExport


class SharedMultiChannelDetectorPlugin:
    """New-style plugin exposing two independent named data channels."""

    params = [create_controller_param(channel_name='ChannelA',
                                        channel_names=['ChannelA', 'ChannelB'])]

    capabilities = None

    def __init__(self):
        self.open_called_with = None
        self.query_calls: list = []
        self.change_calls: list = []
        self._values = {'ChannelA': 1.0, 'ChannelB': 2.0}

    def open(self, settings) -> None:
        self.open_called_with = settings

    def close(self) -> None:
        pass

    def query_data(self, names=None, fresh=True):
        names = list(names) if names else list(self._values.keys())
        self.query_calls.append(names)
        dte = DataToExport('data')
        for name in names:
            dte.append(DataFromPlugins(name=name, data=[np.array([self._values[name]])]))
        return dte

    def change_to(self, name, value) -> None:
        self.change_calls.append((name, value))
        self._values[name] = value

    def commit_settings(self, param) -> None:
        pass


def _load_shared_settings(module, hw_settings_name: str) -> None:
    """Populate *module*'s hw-settings subtree from the shared plugin's params."""
    plugin_params = Parameter.create(
        name=hw_settings_name, type='group',
        children=copy.deepcopy(SharedMultiChannelDetectorPlugin.params),
    )
    for child in module.settings.child(hw_settings_name).children():
        child.remove()
    module.settings.child(hw_settings_name).addChildren(plugin_params.children())


@pytest.fixture(autouse=True)
def _isolated_registry():
    ControllerRegistry._reset_global()
    yield
    ControllerRegistry.get().close_all()
    ControllerRegistry._reset_global()


class TestTwoDAQViewersOnSharedMultiChannelPlugin:
    """Two DAQ_Viewer instances, each bound to a different named channel of
    one shared new-style plugin instance."""

    def setup_method(self):
        self.viewer_a = DAQ_Viewer()
        self.viewer_a._get_plugin_class = lambda: SharedMultiChannelDetectorPlugin
        _load_shared_settings(self.viewer_a, 'detector_settings')
        self.viewer_a.settings.child('detector_settings', 'controller', 'channel').setValue('ChannelA')

        self.viewer_b = DAQ_Viewer()
        self.viewer_b._get_plugin_class = lambda: SharedMultiChannelDetectorPlugin
        _load_shared_settings(self.viewer_b, 'detector_settings')
        self.viewer_b.settings.child('detector_settings', 'controller', 'channel').setValue('ChannelB')

    def teardown_method(self):
        if self.viewer_a._ct is not None:
            self.viewer_a.init_hardware(False)
        if self.viewer_b._ct is not None:
            self.viewer_b.init_hardware(False)

    def _ini_both(self, qtbot):
        self.viewer_a.init_hardware(True)
        qtbot.waitUntil(lambda: self.viewer_a._initialized_state, timeout=3000)

        self.viewer_b.init_hardware(True)
        qtbot.waitUntil(lambda: self.viewer_b._initialized_state, timeout=3000)

    def test_share_same_controller_thread(self, qtbot):
        self._ini_both(qtbot)

        assert self.viewer_a._ct is not None
        assert self.viewer_a._ct is self.viewer_b._ct
        assert ControllerRegistry.get().ref_count(self.viewer_a._ct_key) == 2
        assert self.viewer_a._ct._plugin is self.viewer_b._ct._plugin

    def test_channels_differ_per_viewer(self, qtbot):
        self._ini_both(qtbot)

        assert self.viewer_a._channel == 'ChannelA'
        assert self.viewer_b._channel == 'ChannelB'

    def test_snap_on_a_only_reaches_viewer_a(self, qtbot):
        self._ini_both(qtbot)

        b_calls = []
        self.viewer_b.grab_done_signal.connect(lambda dte: b_calls.append(dte))

        with qtbot.waitSignal(self.viewer_a.grab_done_signal, timeout=3000) as blocker:
            self.viewer_a.snap()

        assert blocker.signal_triggered
        assert b_calls == []
        assert ['ChannelA'] in self.viewer_a._ct._plugin.query_calls

    def test_snap_on_b_only_reaches_viewer_b(self, qtbot):
        self._ini_both(qtbot)

        a_calls = []
        self.viewer_a.grab_done_signal.connect(lambda dte: a_calls.append(dte))

        with qtbot.waitSignal(self.viewer_b.grab_done_signal, timeout=3000) as blocker:
            self.viewer_b.snap()

        assert blocker.signal_triggered
        assert a_calls == []
        assert ['ChannelB'] in self.viewer_b._ct._plugin.query_calls

    def test_detach_one_keeps_ct_alive_for_other(self, qtbot):
        self._ini_both(qtbot)
        key = self.viewer_a._ct_key
        shared_ct = self.viewer_a._ct

        self.viewer_a.init_hardware(False)

        assert ControllerRegistry.get().ref_count(key) == 1
        assert self.viewer_b._ct is shared_ct

        self.viewer_b.init_hardware(False)

        assert ControllerRegistry.get().ref_count(key) == 0
