"""Reproduction: ModulesManager.move_actuators / grab_data busy-wait loops
with CT-based DAQ_Move / DAQ_Viewer, as used by DAQ_Scan at scan end
(``set_ini_positions``) and during a scan step.
"""
from __future__ import annotations

import pytest

from pymodaq.control_modules.daq_move import DAQ_Move
from pymodaq.control_modules.daq_viewer import DAQ_Viewer
from pymodaq.control_modules.controller_registry import ControllerRegistry
from pymodaq.utils.data import DataActuator
from pymodaq.utils.managers.modules.modules_manager import ModulesManager

from .test_daq_move_viewer_shared_ct import SharedCombinedPlugin, _load_shared_settings


@pytest.fixture(autouse=True)
def _isolated_registry():
    ControllerRegistry._reset_global()
    yield
    ControllerRegistry.get().close_all()
    ControllerRegistry._reset_global()


def test_move_actuators_via_modules_manager(qtbot):
    move = DAQ_Move()
    move._get_plugin_class = lambda: SharedCombinedPlugin
    _load_shared_settings(move, 'actuator_settings')
    move.settings.child('actuator_settings', 'controller', 'axis').setValue('X')

    move.init_hardware(True)
    qtbot.waitUntil(lambda: move._initialized_state, timeout=3000)

    mm = ModulesManager(actuators=[move], selected_actuators=[move])

    target = DataActuator(move.title, data=42.0, units=move.units)
    from pymodaq_data.data import DataToExport
    dte_act = DataToExport('Actuators', data=[target])

    mm.connect_actuators()
    result = mm.move_actuators(dte_act, mode='abs', polling=True)
    mm.connect_actuators(False)

    assert mm.move_done_flag is True, "move_actuators timed out (move_done_flag never set)"

    move.init_hardware(False)


def test_grab_data_via_modules_manager_no_leco(qtbot):
    viewer = DAQ_Viewer()
    viewer._get_plugin_class = lambda: SharedCombinedPlugin
    viewer.connect_leco = lambda *a, **k: None  # isolate from LECO listener thread
    _load_shared_settings(viewer, 'detector_settings')

    viewer.init_hardware(True)
    qtbot.waitUntil(lambda: viewer._initialized_state, timeout=3000)

    mm = ModulesManager(detectors=[viewer], selected_detectors=[viewer])

    mm.connect_detectors()
    result = mm.grab_data()
    mm.connect_detectors(False)

    assert mm.det_done_flag is True, "grab_data timed out (det_done_flag never set)"

    viewer.init_hardware(False)


def test_grab_data_via_modules_manager(qtbot):
    viewer = DAQ_Viewer()
    viewer._get_plugin_class = lambda: SharedCombinedPlugin
    _load_shared_settings(viewer, 'detector_settings')

    viewer.init_hardware(True)
    qtbot.waitUntil(lambda: viewer._initialized_state, timeout=3000)

    mm = ModulesManager(detectors=[viewer], selected_detectors=[viewer])

    mm.connect_detectors()
    result = mm.grab_data()
    mm.connect_detectors(False)

    assert mm.det_done_flag is True, "grab_data timed out (det_done_flag never set)"

    viewer.init_hardware(False)
