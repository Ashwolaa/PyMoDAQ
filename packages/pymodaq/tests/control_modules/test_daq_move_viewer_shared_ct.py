"""Integration tests: a real DAQ_Move and a real DAQ_Viewer attached to ONE
shared ControllerThread via the real ControllerRegistry.

This is the X-1 cross-type sharing scenario: a single physical instrument
(here, ``FakeCamera`` driven by ``SharedCombinedPlugin``) is controlled by an
axis (DAQ_Move, channel='X') and a camera (DAQ_Viewer, channel='') at the
same time.  Both modules attach to the SAME ControllerThread/ControllerKey
because they share the same ``hardware_class`` and ``controller_ID``.

Unlike ``test_multi_subscriber_integration.py`` (CT-level only, synchronous,
no QThread), this file exercises the real ``DAQ_Move`` / ``DAQ_Viewer``
module classes and the real ``ControllerRegistry`` (real ``QThread``).
``_get_plugin_class`` is monkeypatched so no entry-point plugin discovery is
needed.
"""
from __future__ import annotations

import copy

import numpy as np
import pytest

from pymodaq_gui.parameter import Parameter

from pymodaq.control_modules.daq_move import DAQ_Move
from pymodaq.control_modules.daq_viewer import DAQ_Viewer
from pymodaq.control_modules.controller_registry import ControllerRegistry
from pymodaq.control_modules.move_utility_classes import comon_parameters
from pymodaq.control_modules.utils import create_controller_param
from pymodaq.utils.data import DataActuator, DataFromPlugins, DataToExport

from .test_multi_subscriber_integration import CombinedCameraPlugin, FakeCamera


# ---------------------------------------------------------------------------
# Combined plugin with a real ``params`` tree (loadable by both Move/Viewer)
# ---------------------------------------------------------------------------

class SharedCombinedPlugin(CombinedCameraPlugin):
    """Combined actuator+detector plugin with a real parameter tree.

    Both ``DAQ_Move`` (``actuator_settings``) and ``DAQ_Viewer``
    (``detector_settings``) load their hw-settings subtree from
    ``SharedCombinedPlugin.params``.  Because both subtrees are built from
    the SAME ``params`` list, ``controller/controller_ID`` resolves to the
    same value for both modules, so they map to the same ``ControllerKey``
    and therefore share one ``ControllerThread``.

    Actuator methods return real ``DataActuator`` instances (instead of the
    ``FakeDataActuator`` used by ``CombinedCameraPlugin``) so they round-trip
    correctly through ``DAQ_Move._check_data_type`` and the strongly-typed
    ``move_done_signal``.
    """

    params = [create_controller_param('X', ['X', 'Y', 'Theta'])] + comon_parameters()

    def _da(self, value: float) -> DataActuator:
        return DataActuator('shared', data=value, units=self.axis_unit)

    def get_actuator_value(self):
        return self._da(self.controller.get_value(self.axis_name))

    def move_abs(self, value):
        v = value.value() if hasattr(value, 'value') else float(value)
        self.controller.set_value(self.axis_name, v)

    def move_home(self):
        self.controller.set_value(self.axis_name, 0.0)

    def stop_motion(self):
        self._emit_move_done(self.get_actuator_value())

    def poll_moving(self):
        self._emit_move_done(self.get_actuator_value())

    def grab_data(self, Naverage=1):
        frame = self.controller.get_data()
        dte = DataToExport('shared', data=[
            DataFromPlugins(name='shared', data=[np.array([list(frame.values())])])])
        for fn in self._dte_listeners:
            fn(dte)


def _load_shared_settings(module, hw_settings_name: str) -> None:
    """Populate *module*'s hw-settings subtree from SharedCombinedPlugin.params."""
    plugin_params = Parameter.create(
        name=hw_settings_name, type='group',
        children=copy.deepcopy(SharedCombinedPlugin.params),
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


class TestDAQMoveAndDAQViewerShareCT:
    """A DAQ_Move (axis X) and a DAQ_Viewer (camera) on the SAME hardware
    attach to the SAME ControllerThread."""

    def setup_method(self):
        self.move = DAQ_Move()
        self.move._get_plugin_class = lambda: SharedCombinedPlugin
        _load_shared_settings(self.move, 'actuator_settings')
        self.move.settings.child('actuator_settings', 'controller', 'axis').setValue('X')

        self.viewer = DAQ_Viewer()
        self.viewer._get_plugin_class = lambda: SharedCombinedPlugin
        _load_shared_settings(self.viewer, 'detector_settings')

    def teardown_method(self):
        if self.move._ct is not None:
            self.move.init_hardware(False)
        if self.viewer._ct is not None:
            self.viewer.init_hardware(False)

    def _ini_both(self, qtbot):
        self.move.init_hardware(True)
        qtbot.waitUntil(lambda: self.move._initialized_state, timeout=3000)

        self.viewer.init_hardware(True)
        qtbot.waitUntil(lambda: self.viewer._initialized_state, timeout=3000)

    def test_share_same_controller_thread(self, qtbot):
        self._ini_both(qtbot)

        assert self.move._ct is not None
        assert self.move._ct is self.viewer._ct
        assert ControllerRegistry.get().ref_count(self.move._ct_key) == 2

    def test_channels_differ_for_axis_and_detector(self, qtbot):
        self._ini_both(qtbot)

        assert self.move._channel == 'X'
        assert self.viewer._channel == ''

    def test_move_abs_changes_hardware_seen_by_detector(self, qtbot):
        """Moving axis X changes the FakeCamera SDK instance shared with the
        detector role of the SAME combined plugin/ControllerThread."""
        self._ini_both(qtbot)
        ct = self.move._ct

        # Both roles operate on the SAME plugin instance / SDK.
        assert ct._plugin is self.viewer._ct._plugin
        assert ct._plugin.controller is self.viewer._ct._plugin.controller

        with qtbot.waitSignal(self.move.move_done_signal, timeout=3000):
            self.move.move_abs(42.0)

        assert ct._plugin.controller.get_value('X') == pytest.approx(42.0)
        # A detector grab on the shared SDK now reflects the new position.
        frame = ct._plugin.controller.get_data()
        assert frame['X'] == pytest.approx(42.0)

    def test_detach_one_keeps_ct_alive_for_other(self, qtbot):
        self._ini_both(qtbot)
        key = self.move._ct_key
        shared_ct = self.move._ct

        self.move.init_hardware(False)

        assert ControllerRegistry.get().ref_count(key) == 1
        assert self.viewer._ct is shared_ct

        self.viewer.init_hardware(False)

        assert ControllerRegistry.get().ref_count(key) == 0
