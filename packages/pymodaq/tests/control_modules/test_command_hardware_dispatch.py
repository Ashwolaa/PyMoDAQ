"""Regression tests for ``command_hardware`` dispatch on CT-based modules.

``command_hardware`` is the legacy cross-thread API used by
``ModulesManager`` (and therefore ``DAQ_Scan`` and other extensions) to
trigger a detector snap/grab (``ControlToHardwareViewer.SINGLE`` /
``GRAB`` / ``STOP_GRAB``) or an actuator move
(``ControlToHardwareMove.MOVE_ABS`` / ``MOVE_REL``).

Before ``ControllerThreadModule._dispatch_command_hardware`` was added,
``command_hardware`` was never connected for CT-based modules, so these
commands went nowhere and ``ModulesManager.grab_data`` /
``ModulesManager.move_actuators`` (used by ``DAQ_Scan``) timed out waiting
for ``grab_done_signal`` / ``move_done_signal``.
"""
from __future__ import annotations

import pytest

from pymodaq_utils.utils import ThreadCommand

from pymodaq.control_modules.daq_move import DAQ_Move
from pymodaq.control_modules.daq_viewer import DAQ_Viewer
from pymodaq.control_modules.controller_registry import ControllerRegistry
from pymodaq.control_modules.thread_commands import ControlToHardwareViewer, ControlToHardwareMove
from pymodaq.utils.data import DataActuator

from .test_daq_move_viewer_shared_ct import SharedCombinedPlugin, _load_shared_settings


@pytest.fixture(autouse=True)
def _isolated_registry():
    ControllerRegistry._reset_global()
    yield
    ControllerRegistry.get().close_all()
    ControllerRegistry._reset_global()


class TestCommandHardwareDispatchViewer:
    def setup_method(self):
        self.viewer = DAQ_Viewer()
        self.viewer._get_plugin_class = lambda: SharedCombinedPlugin
        _load_shared_settings(self.viewer, 'detector_settings')

    def teardown_method(self):
        if self.viewer._ct is not None:
            self.viewer.init_hardware(False)

    def _ini(self, qtbot):
        self.viewer.init_hardware(True)
        qtbot.waitUntil(lambda: self.viewer._initialized_state, timeout=3000)

    def test_single_command_triggers_grab_done(self, qtbot):
        self._ini(qtbot)

        with qtbot.waitSignal(self.viewer.grab_done_signal, timeout=3000):
            self.viewer.command_hardware.emit(
                ThreadCommand(ControlToHardwareViewer.SINGLE, dict(Naverage=1)))

    def test_grab_then_stop_via_command_hardware(self, qtbot):
        self._ini(qtbot)

        with qtbot.waitSignal(self.viewer.grab_status, timeout=3000) as blocker:
            self.viewer.command_hardware.emit(
                ThreadCommand(ControlToHardwareViewer.GRAB, dict(Naverage=1)))
        assert blocker.args[0] is True

        with qtbot.waitSignal(self.viewer.grab_status, timeout=3000) as blocker:
            self.viewer.command_hardware.emit(
                ThreadCommand(ControlToHardwareViewer.STOP_GRAB))
        assert blocker.args[0] is False


class TestCommandHardwareDispatchMove:
    def setup_method(self):
        self.move = DAQ_Move()
        self.move._get_plugin_class = lambda: SharedCombinedPlugin
        _load_shared_settings(self.move, 'actuator_settings')
        self.move.settings.child('actuator_settings', 'controller', 'axis').setValue('X')

    def teardown_method(self):
        if self.move._ct is not None:
            self.move.init_hardware(False)

    def _ini(self, qtbot):
        self.move.init_hardware(True)
        qtbot.waitUntil(lambda: self.move._initialized_state, timeout=3000)

    def test_move_abs_via_command_hardware(self, qtbot):
        self._ini(qtbot)

        target = DataActuator('shared', data=42.0, units=self.move.units)
        with qtbot.waitSignal(self.move.move_done_signal, timeout=3000) as blocker:
            self.move.command_hardware.emit(
                ThreadCommand(command=ControlToHardwareMove.MOVE_ABS, attribute=[target, True]))

        assert blocker.args[0].value() == pytest.approx(42.0, abs=self.move.epsilon)

    def test_move_rel_via_command_hardware(self, qtbot):
        self._ini(qtbot)
        qtbot.waitUntil(lambda: self.move._current_value is not None, timeout=3000)
        start = self.move._current_value.value()

        rel = DataActuator('shared', data=5.0, units=self.move.units)
        with qtbot.waitSignal(self.move.move_done_signal, timeout=3000) as blocker:
            self.move.command_hardware.emit(
                ThreadCommand(command=ControlToHardwareMove.MOVE_REL, attribute=[rel, True]))

        assert blocker.args[0].value() == pytest.approx(start + 5.0, abs=self.move.epsilon)
