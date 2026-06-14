"""Integration tests: multiple DAQ_Move / DAQ_Viewer subscribers on one CT.

One physical instrument → one ControllerThread.  DAQ_Move and DAQ_Viewer are
lightweight subscribers that connect to the same CT and filter by channel.

Scenarios
---------
A. Multi-axis actuator
   Two subscribers (X and Y channels) on one CT with a multi-axis actuator
   plugin.  Channel filtering ensures each subscriber only reacts to its axis.

B. Multi-subscriber detector
   Two DAQ_Viewer-like subscribers on one CT sharing a detector plugin.

C. Combined plugin (the "big fish")
   A single plugin exposes both actuator axes (X, Y, Power) AND a camera
   detector — like the BeamSteering / Camera examples in pymodaq_plugins_mockexamples.
   One CT handles all roles:
     - Multiple DAQ_Move subscribers, each watching one axis channel
     - One DAQ_Viewer subscriber watching the camera channel
   Moving axis X changes the hardware state visible to the next camera grab.

These tests call ini_hardware() synchronously (no QThread).
"""
from __future__ import annotations

import pytest

from pymodaq.control_modules.controller_thread import ControllerThread
from pymodaq.control_modules.controller_registry import ControllerKey, ControllerRegistry
from pymodaq_utils.utils import ThreadCommand


# ---------------------------------------------------------------------------
# Shared hardware SDK mock  (Camera / BeamSteering-style)
# ---------------------------------------------------------------------------

class FakeCamera:
    """Pure-Python hardware SDK: multi-axis stage + camera image.

    Mimics the camera_wrapper.Camera pattern:
    axes X/Y/Theta can be set and read; get_data() returns a snapshot.
    """

    axes = ['X', 'Y', 'Theta']

    def __init__(self):
        self._positions: dict[str, float] = {'X': 0.0, 'Y': 0.0, 'Theta': 0.0}
        self._grab_count: int = 0

    def set_value(self, axis: str, value: float) -> None:
        self._positions[axis] = value

    def get_value(self, axis: str) -> float:
        return self._positions[axis]

    def get_data(self) -> dict:
        """Return a snapshot of current axis positions (stands in for a real image)."""
        self._grab_count += 1
        return dict(self._positions)


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

class FakeDataActuator:
    def __init__(self, value=0.0, units='mm'):
        self.value_float = value
        self.units = units

    def units_as(self, unit):
        return FakeDataActuator(self.value_float, unit)

    def value(self, unit=None):
        return self.value_float


class FakeSettings:
    def saveState(self): return None
    def child(self, *path): return self


class Collector:
    def __init__(self): self.calls: list = []
    def __call__(self, *args): self.calls.append(args)
    @property
    def count(self): return len(self.calls)
    def last(self): return self.calls[-1] if self.calls else None


# ---------------------------------------------------------------------------
# Pure actuator plugin  (multi-axis, dispatches by axis_name)
# ---------------------------------------------------------------------------

class MultiAxisActuatorPlugin:
    """Old-style actuator plugin wrapping FakeCamera axes."""

    hardware_class = FakeCamera
    axis_name: str = 'X'
    axis_unit: str = 'mm'

    class _FloatType:
        def __eq__(self, other):
            from pymodaq.control_modules.move_utility_classes import DataActuatorType
            return other == DataActuatorType.float

    data_actuator_type = _FloatType()

    class _FakeTimer:
        def stop(self): pass

    def __init__(self, parent=None, params_state=None):
        self.parent = parent
        self.controller: FakeCamera = None
        self.move_is_done = False
        self.poll_timer = self._FakeTimer()
        self._move_done_listeners: list = []

    class _Sig:
        def __init__(self, plugin):
            self._plugin = plugin
        def connect(self, fn):
            self._plugin._move_done_listeners.append(fn)

    @property
    def move_done_signal(self): return self._Sig(self)

    def _emit_move_done(self, val):
        for fn in self._move_done_listeners: fn(val)

    def ini_stage(self, controller=None):
        if controller is None:
            controller = FakeCamera()
        self.controller = controller
        return 'ok', True

    def close(self): pass

    def get_actuator_value(self):
        return FakeDataActuator(self.controller.get_value(self.axis_name))

    def move_abs(self, value):
        v = value.value_float if hasattr(value, 'value_float') else float(value)
        self.controller.set_value(self.axis_name, v)

    def move_home(self):
        self.controller.set_value(self.axis_name, 0.0)

    def stop_motion(self):
        self._emit_move_done(FakeDataActuator(self.controller.get_value(self.axis_name)))

    def poll_moving(self):
        self._emit_move_done(FakeDataActuator(self.controller.get_value(self.axis_name)))

    def commit_settings(self, param): pass


# ---------------------------------------------------------------------------
# Pure detector plugin
# ---------------------------------------------------------------------------

class CameraDetectorPlugin:
    """Old-style detector plugin wrapping FakeCamera.get_data()."""

    hardware_class = FakeCamera
    hardware_averaging = False

    def __init__(self, parent=None, params_state=None):
        self.parent = parent
        self.controller: FakeCamera = None
        self._dte_listeners: list = []
        self._dte_temp_listeners: list = []

    class _Sig:
        def __init__(self, lst): self._lst = lst
        def connect(self, fn): self._lst.append(fn)

    @property
    def dte_signal(self): return self._Sig(self._dte_listeners)

    @property
    def dte_signal_temp(self): return self._Sig(self._dte_temp_listeners)

    def ini_detector(self, controller=None):
        if controller is None:
            controller = FakeCamera()
        self.controller = controller
        return 'ok', True

    def grab_data(self, Naverage=1):
        frame = self.controller.get_data()
        for fn in self._dte_listeners: fn(frame)

    def stop(self): pass
    def close(self): pass
    def commit_settings(self, param): pass


# ---------------------------------------------------------------------------
# Detector plugin emitting averagable frames (software averaging tests)
# ---------------------------------------------------------------------------

class AvgFrame:
    """Minimal DataToExport-like object exposing ``.average()``.

    ``CT._on_detector_data_ready`` calls ``dte.average(previous, ind)`` to
    accumulate a running average — mimic that protocol on a plain dict.
    """

    def __init__(self, data: dict):
        self.data = dict(data)

    def average(self, previous: 'AvgFrame', ind: int) -> 'AvgFrame':
        return AvgFrame({
            key: (previous.data[key] * (ind - 1) + value) / ind
            for key, value in self.data.items()
        })


class AveragingCameraPlugin(CameraDetectorPlugin):
    """Old-style detector plugin whose frames support software averaging."""

    def grab_data(self, Naverage=1):
        frame = AvgFrame(self.controller.get_data())
        for fn in self._dte_listeners: fn(frame)


# ---------------------------------------------------------------------------
# Detector plugin with ROI / crosshair hooks
# ---------------------------------------------------------------------------

class ROICrosshairCameraPlugin(CameraDetectorPlugin):
    """Old-style detector plugin recording ROISelect / crosshairChanged calls."""

    def __init__(self, parent=None, params_state=None):
        super().__init__(parent, params_state)
        self.roi_calls: list = []
        self.crosshair_calls: list = []

    def ROISelect(self, roi_info, ind_viewer):
        self.roi_calls.append((roi_info, ind_viewer))

    def crosshairChanged(self, crosshair_info):
        self.crosshair_calls.append(crosshair_info)


class ROIOneArgCameraPlugin(CameraDetectorPlugin):
    """Old-style detector plugin whose ROISelect takes a single argument."""

    def __init__(self, parent=None, params_state=None):
        super().__init__(parent, params_state)
        self.roi_calls: list = []

    def ROISelect(self, roi_info):
        self.roi_calls.append(roi_info)


# ---------------------------------------------------------------------------
# Combined plugin  (the "big fish")
# Exposes both ini_stage (actuator: X/Y/Theta) AND ini_detector (camera grab)
# on the SAME FakeCamera SDK instance — one ControllerThread handles all.
# ---------------------------------------------------------------------------

class CombinedCameraPlugin:
    """Combined plugin: multi-axis stage + camera detector on one SDK.

    Exposes both ini_stage (actuator: X/Y/Theta) and ini_detector (camera grab)
    on the same FakeCamera instance.  ini_stage creates the FakeCamera;
    ini_detector receives it as *controller* so both roles share one SDK.
    One ControllerThread initialises both roles via _ini_combined().
    """

    hardware_class = FakeCamera
    axis_name: str = 'X'
    axis_unit: str = 'mm'
    hardware_averaging = False

    class _FloatType:
        def __eq__(self, other):
            from pymodaq.control_modules.move_utility_classes import DataActuatorType
            return other == DataActuatorType.float

    data_actuator_type = _FloatType()

    class _FakeTimer:
        def stop(self): pass

    def __init__(self, parent=None, params_state=None):
        self.parent = parent
        self.controller: FakeCamera = None
        self.move_is_done = False
        self.poll_timer = self._FakeTimer()
        self._move_done_listeners: list = []
        self._dte_listeners: list = []
        self._dte_temp_listeners: list = []

    # --- signal duck-types (separate classes to avoid name collision) ---------

    class _MoveSig:
        def __init__(self, plugin): self._plugin = plugin
        def connect(self, fn): self._plugin._move_done_listeners.append(fn)

    class _DteSig:
        def __init__(self, lst): self._lst = lst
        def connect(self, fn): self._lst.append(fn)

    @property
    def move_done_signal(self): return self._MoveSig(self)

    @property
    def dte_signal(self): return self._DteSig(self._dte_listeners)

    @property
    def dte_signal_temp(self): return self._DteSig(self._dte_temp_listeners)

    def _emit_move_done(self, val):
        for fn in self._move_done_listeners: fn(val)

    # --- actuator interface --------------------------------------------------

    def ini_stage(self, controller=None):
        if controller is None:
            controller = FakeCamera()
        self.controller = controller
        return 'ok', True

    def get_actuator_value(self):
        return FakeDataActuator(self.controller.get_value(self.axis_name))

    def move_abs(self, value):
        v = value.value_float if hasattr(value, 'value_float') else float(value)
        self.controller.set_value(self.axis_name, v)

    def move_home(self):
        self.controller.set_value(self.axis_name, 0.0)

    def stop_motion(self):
        self._emit_move_done(FakeDataActuator(self.controller.get_value(self.axis_name)))

    def poll_moving(self):
        self._emit_move_done(FakeDataActuator(self.controller.get_value(self.axis_name)))

    # --- detector interface --------------------------------------------------

    def ini_detector(self, controller=None):
        if controller is not None:
            self.controller = controller
        return 'ok', True

    def grab_data(self, Naverage=1):
        frame = self.controller.get_data()
        for fn in self._dte_listeners: fn(frame)

    def stop(self): pass

    # --- shared ----------------------------------------------------------

    def close(self): pass
    def commit_settings(self, param): pass


# ---------------------------------------------------------------------------
# CT factory helpers
# ---------------------------------------------------------------------------

def _make_ct(plugin_cls):
    """Return an uninitialised (ControllerThread, plugin_instance) pair."""
    plugin_instance = plugin_cls()

    class _Cls(plugin_cls):
        def __new__(cls, parent=None, params_state=None):
            plugin_instance.parent = parent
            return plugin_instance

    _Cls.__name__ = plugin_cls.__name__
    ct = ControllerThread(_Cls, FakeSettings())
    return ct, plugin_instance


# ---------------------------------------------------------------------------
# A. Multi-axis actuator: two DAQ_Move subscribers on one CT
# ---------------------------------------------------------------------------

class TestMultiAxisActuator:

    def setup_method(self):
        self.ct, self.plugin = _make_ct(MultiAxisActuatorPlugin)
        self.ct.ini_hardware()

    def _filter(self, channel, col):
        """Return a change_done slot that only records events for *channel*."""
        def slot(ch, val):
            if not ch or ch == channel:
                col(ch, val)
        return slot

    def test_move_x_fires_only_x_subscriber(self, qapp):
        x_col, y_col = Collector(), Collector()
        self.ct.change_done.connect(self._filter('X', x_col))
        self.ct.change_done.connect(self._filter('Y', y_col))

        self.ct.request_write('X', FakeDataActuator(10.0))

        assert x_col.count == 1
        assert y_col.count == 0

    def test_move_y_fires_only_y_subscriber(self, qapp):
        x_col, y_col = Collector(), Collector()
        self.ct.change_done.connect(self._filter('X', x_col))
        self.ct.change_done.connect(self._filter('Y', y_col))

        self.ct.request_write('Y', FakeDataActuator(5.0))

        assert x_col.count == 0
        assert y_col.count == 1

    def test_x_and_y_write_independent_positions(self, qapp):
        self.ct.request_write('X', FakeDataActuator(42.0))
        self.ct.request_write('Y', FakeDataActuator(7.0))

        assert self.plugin.controller.get_value('X') == pytest.approx(42.0)
        assert self.plugin.controller.get_value('Y') == pytest.approx(7.0)

    def test_read_x_returns_x_position(self, qapp):
        self.plugin.controller.set_value('X', 99.0)
        col = Collector()
        self.ct.data_ready.connect(col)
        self.ct.request_read('X')
        assert col.count == 1
        ch, val, is_temp = col.last()
        assert ch == 'X'
        assert val.value_float == pytest.approx(99.0)

    def test_all_subscribers_see_same_sdk(self, qapp):
        self.ct.request_write('X', FakeDataActuator(1.0))
        self.ct.request_write('Y', FakeDataActuator(2.0))
        sdk = self.plugin.controller
        assert sdk.get_value('X') == pytest.approx(1.0)
        assert sdk.get_value('Y') == pytest.approx(2.0)
        assert self.ct._controller is sdk


# ---------------------------------------------------------------------------
# B. Multi-subscriber detector: two DAQ_Viewer subscribers on one CT
# ---------------------------------------------------------------------------

class TestMultiSubscriberDetector:

    def setup_method(self):
        self.ct, self.plugin = _make_ct(CameraDetectorPlugin)
        self.ct.ini_hardware()

    def test_both_subscribers_receive_data_ready(self, qapp):
        col_a, col_b = Collector(), Collector()
        self.ct.data_ready.connect(col_a)
        self.ct.data_ready.connect(col_b)

        self.ct.request_snap('', 1)

        assert col_a.count == 1
        assert col_b.count == 1

    def test_channel_filter_routes_correctly(self, qapp):
        cam_col, ir_col = Collector(), Collector()

        def cam_slot(ch, data, is_temp):
            if not ch or ch == 'cam': cam_col(ch, data, is_temp)

        def ir_slot(ch, data, is_temp):
            if not ch or ch == 'ir': ir_col(ch, data, is_temp)

        self.ct.data_ready.connect(cam_slot)
        self.ct.data_ready.connect(ir_slot)

        self.ct.request_snap('cam', 1)

        assert cam_col.count == 1
        assert ir_col.count == 0   # 'ir' filtered out

    def test_hardware_grab_count_matches_snap_calls(self, qapp):
        for _ in range(3):
            self.ct.request_snap('', 1)
        assert self.plugin.controller._grab_count == 3


# ---------------------------------------------------------------------------
# B2. Software averaging (set_averaging + chained grab_data)
# ---------------------------------------------------------------------------

class TestSoftwareAveraging:

    def setup_method(self):
        self.ct, self.plugin = _make_ct(AveragingCameraPlugin)
        self.ct.ini_hardware()

    def test_naverage_1_is_passthrough(self, qapp):
        self.ct.set_averaging('', 1)
        col = Collector()
        self.ct.data_ready.connect(col)

        self.ct.request_snap('', 1)

        assert self.plugin.controller._grab_count == 1
        assert col.count == 1
        _, _, is_temp = col.last()
        assert is_temp is False

    def test_naverage_3_chains_grabs_and_emits_once(self, qapp):
        self.ct.set_averaging('', 3)
        col = Collector()
        self.ct.data_ready.connect(col)

        self.ct.request_snap('', 1)

        assert self.plugin.controller._grab_count == 3
        assert col.count == 1
        _, _, is_temp = col.last()
        assert is_temp is False

    def test_show_intermediate_emits_temp_frames(self, qapp):
        self.ct.set_averaging('', 3, show_intermediate=True)
        col = Collector()
        self.ct.data_ready.connect(col)

        self.ct.request_snap('', 1)

        # One temp frame per accumulated grab (3) plus the final averaged frame.
        assert col.count == 4
        assert [c[2] for c in col.calls] == [True, True, True, False]

    def test_averaging_of_constant_value(self, qapp):
        self.plugin.controller.set_value('X', 7.0)
        self.ct.set_averaging('', 3)
        col = Collector()
        self.ct.data_ready.connect(col)

        self.ct.request_snap('', 1)

        _, frame, _ = col.last()
        assert frame.data['X'] == pytest.approx(7.0)

    def test_set_averaging_back_to_1_clears_state(self, qapp):
        self.ct.set_averaging('', 3)
        assert '' in self.ct._averaging

        self.ct.set_averaging('', 1)

        assert '' not in self.ct._averaging


# ---------------------------------------------------------------------------
# B3. Continuous grab via start_grab / stop_grab (QTimer-driven)
# ---------------------------------------------------------------------------

class TestContinuousGrab:

    def setup_method(self):
        self.ct, self.plugin = _make_ct(CameraDetectorPlugin)
        self.ct.ini_hardware()

    def teardown_method(self):
        # Make sure no leftover timers keep firing into the next test.
        rg = self.ct._groups.get('')
        if rg is not None:
            for ch in list(rg.channels):
                self.ct.stop_grab(ch)

    def test_start_grab_emits_periodically(self, qtbot):
        col = Collector()
        self.ct.data_ready.connect(col)

        self.ct.start_grab('', 20)
        qtbot.waitUntil(lambda: col.count >= 2, timeout=2000)
        self.ct.stop_grab('')

        assert self.plugin.controller._grab_count >= 2

    def test_stop_grab_stops_timer(self, qtbot):
        col = Collector()
        self.ct.data_ready.connect(col)

        self.ct.start_grab('', 20)
        qtbot.waitUntil(lambda: col.count >= 1, timeout=2000)
        self.ct.stop_grab('')

        count_after_stop = col.count
        qtbot.wait(100)

        assert col.count == count_after_stop

    def test_fastest_subscriber_wins_period(self, qtbot):
        self.ct.start_grab('', 200)
        self.ct.start_grab('', 20)

        rg = self.ct._groups['']
        assert rg.channels[''].period_ms == pytest.approx(20)

        self.ct.stop_grab('')
        self.ct.stop_grab('')

        assert '' not in self.ct._groups


# ---------------------------------------------------------------------------
# B4. ROI / crosshair forwarding to the plugin
# ---------------------------------------------------------------------------

class TestROIAndCrosshair:

    def test_roi_select_forwarded_with_ind_viewer(self, qapp):
        ct, plugin = _make_ct(ROICrosshairCameraPlugin)
        ct.ini_hardware()

        ct.request_roi_select('', {'roi': 1}, 2)

        assert plugin.roi_calls == [({'roi': 1}, 2)]

    def test_crosshair_forwarded(self, qapp):
        ct, plugin = _make_ct(ROICrosshairCameraPlugin)
        ct.ini_hardware()

        ct.request_crosshair('', {'pos': (1, 2)}, 0)

        assert plugin.crosshair_calls == [{'pos': (1, 2)}]

    def test_roi_select_one_arg_signature(self, qapp):
        ct, plugin = _make_ct(ROIOneArgCameraPlugin)
        ct.ini_hardware()

        ct.request_roi_select('', {'roi': 1}, 5)

        assert plugin.roi_calls == [{'roi': 1}]

    def test_roi_select_missing_method_silently_ignored(self, qapp):
        ct, plugin = _make_ct(CameraDetectorPlugin)
        ct.ini_hardware()

        ct.request_roi_select('', {'roi': 1}, 0)  # no ROISelect on plugin: no-op

    def test_crosshair_missing_method_silently_ignored(self, qapp):
        ct, plugin = _make_ct(CameraDetectorPlugin)
        ct.ini_hardware()

        ct.request_crosshair('', {'pos': (0, 0)}, 0)  # no crosshairChanged: no-op


# ---------------------------------------------------------------------------
# C. Combined plugin: multiple DAQ_Move + DAQ_Viewer on ONE CT
# ---------------------------------------------------------------------------

class TestCombinedPlugin:
    """One ControllerThread owns a combined plugin (actuator + detector).

    Subscribes:
      - DAQ_Move_X  (channel='X')
      - DAQ_Move_Y  (channel='Y')
      - DAQ_Viewer  (channel='', broadcast)
    """

    def setup_method(self):
        self.ct, self.plugin = _make_ct(CombinedCameraPlugin)
        self.ct.ini_hardware()
        # Verify both roles initialised on the same SDK
        assert self.ct._plugin is self.plugin
        assert self.ct._controller is self.plugin.controller

    def _move_filter(self, channel, col):
        def slot(ch, val):
            if not ch or ch == channel: col(ch, val)
        return slot

    # -- Actuator tests -------------------------------------------------------

    def test_move_x_fires_only_x_subscriber(self, qapp):
        x_col, y_col = Collector(), Collector()
        self.ct.change_done.connect(self._move_filter('X', x_col))
        self.ct.change_done.connect(self._move_filter('Y', y_col))

        self.ct.request_write('X', FakeDataActuator(20.0))

        assert x_col.count == 1
        assert y_col.count == 0

    def test_move_y_fires_only_y_subscriber(self, qapp):
        x_col, y_col = Collector(), Collector()
        self.ct.change_done.connect(self._move_filter('X', x_col))
        self.ct.change_done.connect(self._move_filter('Y', y_col))

        self.ct.request_write('Y', FakeDataActuator(15.0))

        assert x_col.count == 0
        assert y_col.count == 1

    def test_three_axis_positions_independent(self, qapp):
        self.ct.request_write('X', FakeDataActuator(1.0))
        self.ct.request_write('Y', FakeDataActuator(2.0))
        sdk = self.plugin.controller
        sdk.set_value('Theta', 45.0)   # set directly (no DAQ_Move for Theta here)

        assert sdk.get_value('X') == pytest.approx(1.0)
        assert sdk.get_value('Y') == pytest.approx(2.0)
        assert sdk.get_value('Theta') == pytest.approx(45.0)

    # -- Detector tests -------------------------------------------------------

    def test_snap_emits_data_ready(self, qapp):
        col = Collector()
        self.ct.data_ready.connect(col)
        self.ct.request_snap('', 1)
        assert col.count == 1

    def test_grab_data_not_confused_with_actuator_read(self, qapp):
        """request_snap goes to grab_data, not get_actuator_value."""
        col = Collector()
        self.ct.data_ready.connect(col)
        self.ct.request_snap('', 1)
        _, frame, is_temp = col.last()
        assert isinstance(frame, dict)   # FakeCamera.get_data() returns dict
        assert is_temp is False

    # -- Cross-role tests: move then grab -------------------------------------

    def test_move_x_visible_in_next_grab(self, qapp):
        """Moving X on the actuator role changes what the detector grab observes."""
        self.ct.request_write('X', FakeDataActuator(88.0))
        assert self.plugin.controller.get_value('X') == pytest.approx(88.0)

        data_col = Collector()
        self.ct.data_ready.connect(data_col)
        self.ct.request_snap('', 1)

        _, frame, _ = data_col.last()
        assert frame['X'] == pytest.approx(88.0)

    def test_move_y_then_grab_reflects_new_y(self, qapp):
        self.ct.request_write('Y', FakeDataActuator(-5.0))

        data_col = Collector()
        self.ct.data_ready.connect(data_col)
        self.ct.request_snap('', 1)

        _, frame, _ = data_col.last()
        assert frame['Y'] == pytest.approx(-5.0)

    def test_actuator_and_detector_subscribers_on_independent_signals(self, qapp):
        """change_done does not appear in data_ready and vice-versa."""
        change_col = Collector()
        data_col = Collector()
        self.ct.change_done.connect(change_col)
        self.ct.data_ready.connect(data_col)

        self.ct.request_write('X', FakeDataActuator(1.0))
        self.ct.request_snap('', 1)

        assert change_col.count == 1   # actuator move
        assert data_col.count == 1     # detector grab


# ---------------------------------------------------------------------------
# D. Registry: same hardware_class → same CT for all subscribers
# ---------------------------------------------------------------------------

class FakeThread:
    def __init__(self): self.close_hardware_called = False
    def close_hardware(self): self.close_hardware_called = True


class FakeRegistryForIntegration(ControllerRegistry):
    def _make_settings(self, plugin_class, params_state, exclude_params=frozenset()):
        class _S:
            def saveState(self): return None
            def child(self, *p): return self
        return _S()

    def _make_thread(self, plugin_class, settings):
        return FakeThread()


class TestRegistrySameHardwareSharesCT:

    def _hw(self, name='FakeHW'):
        return type(name, (), {})

    def _cls(self, name, hw):
        return type(name, (), {'hardware_class': hw, 'params': []})

    def test_same_plugin_class_returns_same_thread(self):
        reg = FakeRegistryForIntegration()
        hw = self._hw()
        cls = self._cls('DAQ_Move_X', hw)
        key = ControllerKey(hardware_class=hw, controller_id=0)

        t1, _ = reg.attach(key, cls, subscriber='sub1')
        t2, _ = reg.attach(key, cls, subscriber='sub2')

        assert t1 is t2
        assert reg.ref_count(key) == 2

    def test_actuator_and_detector_plugin_same_hardware_share_thread(self):
        """DAQ_Move and DAQ_Viewer with the same hardware_class share ONE CT."""
        reg = FakeRegistryForIntegration()
        hw = self._hw('BeamSteering')
        move_cls = self._cls('DAQ_Move_BS', hw)
        view_cls = self._cls('DAQ_Viewer_BS', hw)

        key = ControllerKey(hardware_class=hw, controller_id=0)
        t_move, _ = reg.attach(key, move_cls)
        t_view, _ = reg.attach(key, view_cls)

        assert t_move is t_view   # ONE thread for the instrument
        assert reg.ref_count(key) == 2

    def test_different_controller_ids_give_different_threads(self):
        reg = FakeRegistryForIntegration()
        hw = self._hw()
        cls = self._cls('DAQ_Move', hw)

        key0 = ControllerKey(hardware_class=hw, controller_id=0)
        key1 = ControllerKey(hardware_class=hw, controller_id=1)

        t0, _ = reg.attach(key0, cls)
        t1, _ = reg.attach(key1, cls)

        assert t0 is not t1   # two physical instruments


# ---------------------------------------------------------------------------
# E. Refresh-while-moving: axis restoration after a read on a different channel
# ---------------------------------------------------------------------------

class MultiAxisWithPendingMove(MultiAxisActuatorPlugin):
    """Variant of MultiAxisActuatorPlugin where poll_moving() does NOT
    immediately call move_done — it just records the move as in-flight,
    simulating a slow hardware move.  check_target_reached() must be
    called explicitly by the test to resolve the move."""

    def __init__(self, parent=None, params_state=None):
        super().__init__(parent, params_state)
        self.get_actuator_value_calls: list[str] = []

    def poll_moving(self):
        """Start polling without immediately completing — let the test drive it."""
        pass  # no immediate move_done

    def get_actuator_value(self):
        self.get_actuator_value_calls.append(self.axis_name)
        return FakeDataActuator(self.controller.get_value(self.axis_name))


class TestRefreshWhileMoving:
    """Verify that a refresh read on channel Y while a move on channel X is
    in progress does NOT leave the plugin's axis pointing at Y, which would
    cause check_target_reached() to poll the wrong hardware position."""

    def setup_method(self):
        self.ct, self.plugin = _make_ct(MultiAxisWithPendingMove)
        self.ct.ini_hardware()

    def test_plugin_axis_restored_to_pending_after_refresh_read(self, qapp):
        """After request_read('Y') during a move on 'X', plugin axis == 'X'."""
        # Simulate a move in-flight on X
        self.ct._pending_channel = 'X'
        self.plugin.axis_name = 'X'

        self.ct._read_old_style_actuator('Y')

        assert self.plugin.axis_name == 'X', (
            "Plugin axis must be restored to the pending move channel after a refresh read"
        )

    def test_refresh_read_still_emits_correct_channel_data(self, qapp):
        """data_ready still carries the correct channel and position for Y,
        even though we restore the plugin axis to X afterwards."""
        self.plugin.controller.set_value('X', 1.0)
        self.plugin.controller.set_value('Y', 99.0)
        self.ct._pending_channel = 'X'
        self.plugin.axis_name = 'X'

        col = Collector()
        self.ct.data_ready.connect(col)
        self.ct._read_old_style_actuator('Y')

        assert col.count == 1
        ch, val, _ = col.last()
        assert ch == 'Y'
        assert val.value_float == pytest.approx(99.0)
        # And axis is back on X
        assert self.plugin.axis_name == 'X'

    def test_group_tick_restores_axis_after_multi_channel_read(self, qapp):
        """_on_group_tick reads X then Y; plugin must be restored to X (pending)
        so that check_target_reached polls X, not Y."""
        self.plugin.controller.set_value('X', 5.0)
        self.plugin.controller.set_value('Y', 42.0)
        self.ct._pending_channel = 'X'
        self.plugin.axis_name = 'X'

        # Register both channels in the default group
        self.ct.start_grab('X', 200.0)
        self.ct.start_grab('Y', 200.0)

        # Fire one group tick manually (both channels)
        self.ct._on_group_tick('')

        assert self.plugin.axis_name == 'X', (
            "After group tick reading X and Y, plugin must be back on the pending channel X"
        )

    def test_get_actuator_value_reads_pending_channel_after_refresh(self, qapp):
        """When check_target_reached calls get_actuator_value() after a Y refresh,
        it must read X's position, not Y's."""
        self.plugin.controller.set_value('X', 10.0)
        self.plugin.controller.set_value('Y', 999.0)
        self.ct._pending_channel = 'X'
        self.plugin.axis_name = 'X'

        self.plugin.get_actuator_value_calls.clear()
        self.ct._read_old_style_actuator('Y')

        # Simulate what check_target_reached does next: read current position
        val = self.plugin.get_actuator_value()

        assert val.value_float == pytest.approx(10.0), (
            "After restoring axis to X, get_actuator_value must return X's position"
        )

    def test_no_restore_when_no_pending_move(self, qapp):
        """When there is no in-flight move (_pending_channel=''), a refresh read
        on Y leaves the plugin on Y (normal one-shot read behaviour)."""
        self.ct._pending_channel = ''
        self.plugin.axis_name = 'X'

        self.ct._read_old_style_actuator('Y')

        assert self.plugin.axis_name == 'Y'

    def test_no_restore_when_pending_is_same_channel(self, qapp):
        """When the refresh read is for the same channel as the pending move,
        no restoration is needed (and none should happen)."""
        self.ct._pending_channel = 'Y'
        self.plugin.axis_name = 'X'  # starts elsewhere

        self.ct._read_old_style_actuator('Y')

        assert self.plugin.axis_name == 'Y'

    def test_emit_channel_state_suppresses_duplicate_units(self, qapp):
        """During a group tick, _emit_channel_state must suppress units that
        haven't changed — this is the root cause of spinbox focus loss when two
        DAQ_Move instances both run refresh value on the same CT.

        Suppression is scoped to group-tick context (_in_group_tick=True) so
        that explicit request_read() calls always emit (a subscriber freshly
        attached to a channel still gets notified).
        """
        col = Collector()
        self.ct.settings_changed.connect(col)
        self.plugin.axis_name = 'X'

        # Simulate being inside a group tick.
        self.ct._in_group_tick = True

        # First call inside tick: unit is new → must emit.
        self.ct._emit_channel_state('X')
        assert col.count == 1, "First call for X inside group tick should emit"

        # Second call, same unit, same tick → suppress.
        self.ct._emit_channel_state('X')
        assert col.count == 1, "Duplicate emission during group tick must be suppressed"

        # Different channel Y: must emit (new channel).
        self.plugin.axis_name = 'Y'
        self.ct._emit_channel_state('Y')
        assert col.count == 2, "New channel Y inside group tick should emit"

        # Y again, same tick → suppress.
        self.ct._emit_channel_state('Y')
        assert col.count == 2, "Duplicate emission for Y during group tick must be suppressed"

        # Outside group tick: always emit, even for already-seen units.
        self.ct._in_group_tick = False
        self.ct._emit_channel_state('X')
        assert col.count == 3, "Outside group tick, emit always fires even for same units"

    def test_group_tick_does_not_spam_settings_changed(self, qapp):
        """Multiple group ticks must not keep firing settings_changed for units
        that haven't changed — simulates both DAQ_Move instances refreshing."""
        col = Collector()
        self.ct.settings_changed.connect(col)
        self.plugin.controller.set_value('X', 1.0)
        self.plugin.controller.set_value('Y', 2.0)
        self.plugin.axis_name = 'X'

        self.ct.start_grab('X', 200.0)
        self.ct.start_grab('Y', 200.0)

        # Run several ticks
        for _ in range(5):
            self.ct._on_group_tick('')

        # settings_changed for units should fire at most once per channel
        # (on the first tick that reads each channel), never more.
        units_events = [c for c in col.calls if c[1] == ['units']]
        channels_seen = {e[0] for e in units_events}
        for ch in channels_seen:
            count = sum(1 for e in units_events if e[0] == ch)
            assert count == 1, (
                f"settings_changed(units) for channel '{ch}' fired {count} times "
                f"across 5 ticks — should be exactly 1"
            )


# ---------------------------------------------------------------------------
# Custom command forwarding
# ---------------------------------------------------------------------------

class TestCustomCommand:
    """CT.custom_command forwards unhandled plugin ThreadCommands to subscribers.

    Plugins call emit_status(ThreadCommand('update_main_settings', ...)) (or
    'show_splash' / 'close_splash' / 'lcd') to communicate with the DAQ module.
    In the old DetectorWorker path these commands arrived via status_sig →
    thread_status().  In the CT path _StatusSig.emit must relay them through
    CT.custom_command so subscribers can handle them via thread_status().
    """

    def setup_method(self):
        self.ct, self.plugin = _make_ct(CameraDetectorPlugin)
        self.ct.ini_hardware()

    def test_update_main_settings_forwarded(self, qapp):
        """'update_main_settings' ThreadCommand must arrive on custom_command."""
        received = []
        self.ct.custom_command.connect(lambda cmd: received.append(cmd))

        cmd = ThreadCommand('update_main_settings', [['wait_time'], 100, 'value'])
        self.ct._plugin.parent.status_sig.emit(cmd)

        assert len(received) == 1
        assert received[0].command == 'update_main_settings'
        assert received[0].attribute == [['wait_time'], 100, 'value']

    def test_show_splash_forwarded(self, qapp):
        """'show_splash' ThreadCommand must arrive on custom_command."""
        received = []
        self.ct.custom_command.connect(lambda cmd: received.append(cmd))

        cmd = ThreadCommand('show_splash', 'Initialising...')
        self.ct._plugin.parent.status_sig.emit(cmd)

        assert len(received) == 1
        assert received[0].command == 'show_splash'

    def test_close_splash_forwarded(self, qapp):
        """'close_splash' with no attribute must still arrive on custom_command."""
        received = []
        self.ct.custom_command.connect(lambda cmd: received.append(cmd))

        cmd = ThreadCommand('close_splash')
        self.ct._plugin.parent.status_sig.emit(cmd)

        assert len(received) == 1
        assert received[0].command == 'close_splash'

    def test_update_settings_not_doubled(self, qapp):
        """'update_settings' is handled by settings_changed, NOT custom_command."""
        custom_received = []
        settings_received = []
        self.ct.custom_command.connect(lambda cmd: custom_received.append(cmd))
        self.ct.settings_changed.connect(lambda *a: settings_received.append(a))

        cmd = ThreadCommand('update_settings', [['some', 'path'], 42, 'value'])
        self.ct._plugin.parent.status_sig.emit(cmd)

        assert len(settings_received) == 1, "update_settings must fire settings_changed"
        assert len(custom_received) == 0, "update_settings must NOT fire custom_command"

    def test_check_position_not_forwarded_to_custom(self, qapp):
        """Position updates go to data_ready, NOT custom_command."""
        custom_received = []
        self.ct.custom_command.connect(lambda cmd: custom_received.append(cmd))

        from pymodaq.utils.data import DataActuator
        da = DataActuator(data=5.0)
        cmd = ThreadCommand('check_position', da)
        self.ct._plugin.parent.status_sig.emit(cmd)

        assert len(custom_received) == 0, "check_position must NOT fire custom_command"
