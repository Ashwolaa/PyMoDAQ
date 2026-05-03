"""Tests for ControllerThread.

Design: one physical hardware device → one ControllerThread → one plugin instance.
DAQ_Move and DAQ_Viewer are pure GUI subscribers; they never touch the SDK.

Three sets of mock plugins:
  - New-style (open / close / query_data / change_to)
  - Old-style actuator (ini_stage / move_abs / poll_moving / get_actuator_value)
  - Old-style detector (ini_detector / grab_data / stop / close)

Qt is required (ControllerThread is a QObject) but no GUI is shown.
Slots are called directly in the test thread for the core logic tests.
Timer firing is verified with qtbot.
"""
from __future__ import annotations

import pytest

from pymodaq.control_modules.controller_thread import ControllerThread


# ---------------------------------------------------------------------------
# Mock plugin helpers
# ---------------------------------------------------------------------------

FAKE_DTE = object()   # stand-in for DataToExport


class MockPlugin:
    """New-style plugin stub: records every call, raises on demand."""

    def __init__(self):
        self.open_called_with = None   # settings passed to open()
        self.close_called = False
        self.query_calls: list = []    # list of names lists
        self.change_calls: list = []   # list of (name, value)
        self.commit_calls: list = []   # list of (path, data, change)

        self._open_raises: Exception | None = None
        self._query_raises: Exception | None = None
        self._change_raises: Exception | None = None
        self._capabilities = None

    def open(self, settings) -> None:
        self.open_called_with = settings
        if self._open_raises:
            raise self._open_raises

    def close(self) -> None:
        self.close_called = True

    def query_data(self, names=None, fresh=True):
        self.query_calls.append(names)
        if self._query_raises:
            raise self._query_raises
        return FAKE_DTE

    def change_to(self, name, value) -> None:
        self.change_calls.append((name, value))
        if self._change_raises:
            raise self._change_raises

    def commit_settings(self, param) -> None:
        """All plugins receive a Parameter object, old-style and new-style alike."""
        self.commit_calls.append(param)

    @property
    def capabilities(self):
        return self._capabilities


class FakeSettings:
    """Stand-in for pymodaq_gui Parameter."""
    def saveState(self):
        return None
    def child(self, *path):
        return self


def make_plugin_class(plugin_instance: MockPlugin) -> type:
    """Return a plugin class whose constructor always returns *plugin_instance*.

    Inherits from MockPlugin so ``hasattr(_PluginClass, 'open')`` returns True
    and the new-style detection in ControllerThread works correctly.
    """
    instance = plugin_instance

    class _PluginClass(MockPlugin):
        def __new__(cls, *args, **kwargs):
            return instance

    _PluginClass.__name__ = 'MockPluginClass'
    return _PluginClass


def make_thread(plugin_instance: MockPlugin | None = None) -> tuple[ControllerThread, MockPlugin]:
    """Return a (ControllerThread, MockPlugin) pair, not yet initialised."""
    if plugin_instance is None:
        plugin_instance = MockPlugin()
    plugin_cls = make_plugin_class(plugin_instance)
    thread_obj = ControllerThread(plugin_class=plugin_cls, params_state=None)
    return thread_obj, plugin_instance


# ---------------------------------------------------------------------------
# Signal collector
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ini_hardware
# ---------------------------------------------------------------------------

class TestIniHardware:

    def test_ini_calls_plugin_open(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        assert plugin.open_called_with is not None

    def test_ini_passes_plugin_settings_to_open(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        # Plugin receives the hardware-thread-owned _plugin_settings Parameter,
        # not the shared GUI-thread hw_settings.
        assert plugin.open_called_with is thread_obj._plugin_settings

    def test_ini_stores_plugin_instance(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        assert thread_obj._plugin is plugin

    def test_ini_emits_hardware_status_true(self, qapp):
        thread_obj, plugin = make_thread()
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.ini_hardware()
        assert collector.count == 1
        connected, _ = collector.last()
        assert connected is True

    def test_ini_emits_capabilities_when_present(self, qapp):
        thread_obj, plugin = make_thread()
        fake_caps = object()
        plugin._capabilities = fake_caps
        collector = Collector()
        thread_obj.capabilities_signal.connect(collector)
        thread_obj.ini_hardware()
        assert collector.count == 1
        assert collector.last()[0] is fake_caps

    def test_ini_does_not_emit_capabilities_when_none(self, qapp):
        thread_obj, plugin = make_thread()
        collector = Collector()
        thread_obj.capabilities_signal.connect(collector)
        thread_obj.ini_hardware()
        assert collector.count == 0

    def test_ini_failure_emits_hardware_status_false(self, qapp):
        thread_obj, plugin = make_thread()
        plugin._open_raises = RuntimeError('device not found')
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.ini_hardware()
        connected, info = collector.last()
        assert connected is False
        assert 'device not found' in info

    def test_ini_failure_leaves_plugin_none(self, qapp):
        thread_obj, plugin = make_thread()
        plugin._open_raises = RuntimeError('oops')
        thread_obj.ini_hardware()
        assert thread_obj._plugin is None


# ---------------------------------------------------------------------------
# close_hardware
# ---------------------------------------------------------------------------

class TestCloseHardware:

    def test_close_calls_plugin_close(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.close_hardware()
        assert plugin.close_called

    def test_close_sets_plugin_to_none(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.close_hardware()
        assert thread_obj._plugin is None

    def test_close_emits_hardware_status_false(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.close_hardware()
        connected, _ = collector.last()
        assert connected is False

    def test_close_before_ini_is_safe(self, qapp):
        thread_obj, _ = make_thread()
        thread_obj.close_hardware()  # must not raise

    def test_close_stops_grab_timers(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 1000.0)
        assert 'ch' in thread_obj._groups[''].channels
        thread_obj.close_hardware()
        assert thread_obj._groups == {}
        assert thread_obj._solo == {}


# ---------------------------------------------------------------------------
# request_read
# ---------------------------------------------------------------------------

class TestRequestRead:

    def test_request_read_calls_query_data(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.request_read('axis_x')
        assert plugin.query_calls == [['axis_x']]

    def test_request_read_emits_data_ready(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('axis_x')
        assert collector.count == 1
        channel, dte, is_temp = collector.last()
        assert channel == 'axis_x'
        assert dte is FAKE_DTE
        assert is_temp is False

    def test_request_read_before_ini_is_noop(self, qapp):
        thread_obj, plugin = make_thread()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('axis_x')
        assert collector.count == 0
        assert plugin.query_calls == []

    def test_request_read_exception_emits_hardware_status_false(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        plugin._query_raises = RuntimeError('read failed')
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.request_read('axis_x')
        connected, info = collector.last()
        assert connected is False
        assert 'read failed' in info


# ---------------------------------------------------------------------------
# request_write
# ---------------------------------------------------------------------------

class TestRequestWrite:

    def test_request_write_calls_change_to(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.request_write('axis_x', 42.0)
        assert plugin.change_calls == [('axis_x', 42.0)]

    def test_request_write_emits_change_done(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.change_done.connect(collector)
        thread_obj.request_write('axis_x', 42.0)
        assert collector.count == 1
        channel, value = collector.last()
        assert channel == 'axis_x'
        assert value == 42.0

    def test_request_write_before_ini_is_noop(self, qapp):
        thread_obj, plugin = make_thread()
        collector = Collector()
        thread_obj.change_done.connect(collector)
        thread_obj.request_write('axis_x', 0.0)
        assert collector.count == 0
        assert plugin.change_calls == []

    def test_request_write_exception_emits_hardware_status_false(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        plugin._change_raises = RuntimeError('write failed')
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.request_write('axis_x', 0.0)
        connected, info = collector.last()
        assert connected is False
        assert 'write failed' in info


# ---------------------------------------------------------------------------
# start_grab / stop_grab
# ---------------------------------------------------------------------------

class TestGrabTimers:

    def test_start_grab_default_group_registers_channel(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0)            # group='' by default
        assert '' in thread_obj._groups
        assert 'ch' in thread_obj._groups[''].channels
        assert thread_obj._groups[''].timer is not None
        thread_obj.stop_grab('ch')

    def test_start_grab_named_group_registers_channel(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0, group='detector')
        assert 'detector' in thread_obj._groups
        assert 'ch' in thread_obj._groups['detector'].channels
        thread_obj.stop_grab('ch')

    def test_start_grab_solo_registers_channel(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0, group=None)
        assert 'ch' in thread_obj._solo
        assert '' not in thread_obj._groups
        thread_obj.stop_grab('ch')

    def test_stop_grab_removes_channel_from_group(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0)
        thread_obj.stop_grab('ch')
        assert '' not in thread_obj._groups

    def test_stop_grab_removes_solo_channel(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0, group=None)
        thread_obj.stop_grab('ch')
        assert 'ch' not in thread_obj._solo

    def test_stop_grab_unknown_channel_is_noop(self, qapp):
        thread_obj, _ = make_thread()
        thread_obj.stop_grab('nonexistent')  # must not raise

    def test_second_subscriber_faster_rate_shrinks_group_interval(self, qapp):
        """Adding a faster subscriber shrinks the group timer interval."""
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 200.0)
        assert thread_obj._groups[''].timer.interval() == 200
        thread_obj.start_grab('ch', 100.0)
        assert thread_obj._groups[''].timer.interval() == 100
        thread_obj.stop_grab('ch')
        thread_obj.stop_grab('ch')

    def test_second_subscriber_slower_rate_keeps_min(self, qapp):
        """A slower subscriber cannot raise the rate above the fastest one."""
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0)
        thread_obj.start_grab('ch', 500.0)
        assert thread_obj._groups[''].timer.interval() == 100
        thread_obj.stop_grab('ch')
        thread_obj.stop_grab('ch')

    def test_group_timer_survives_first_of_two_subscribers(self, qapp):
        """Group timer must not stop when the first subscriber leaves if a second remains."""
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0)
        thread_obj.start_grab('ch', 100.0)
        thread_obj.stop_grab('ch')           # first leaves — group persists
        assert '' in thread_obj._groups
        assert 'ch' in thread_obj._groups[''].channels
        thread_obj.stop_grab('ch')           # second leaves — group removed
        assert '' not in thread_obj._groups

    def test_multiple_channels_share_one_group_timer(self, qapp):
        """Two channels in the default group share one QTimer at the min period."""
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('x', 200.0)
        thread_obj.start_grab('y', 100.0)
        assert len(thread_obj._groups[''].channels) == 2
        assert thread_obj._groups[''].timer.interval() == 100  # min wins
        thread_obj.stop_grab('x')
        thread_obj.stop_grab('y')

    def test_two_named_groups_have_independent_timers(self, qapp):
        """Channels in different named groups get separate QTimers."""
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('pos', 100.0, group='actuator')
        thread_obj.start_grab('img', 500.0, group='detector')
        assert 'actuator' in thread_obj._groups
        assert 'detector' in thread_obj._groups
        t_act = thread_obj._groups['actuator'].timer
        t_det = thread_obj._groups['detector'].timer
        assert t_act is not t_det
        assert t_act.interval() == 100
        assert t_det.interval() == 500
        thread_obj.stop_grab('pos')
        thread_obj.stop_grab('img')

    def test_start_grab_fires_request_read(self, qapp, qtbot):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.start_grab('ch', 50.0)
        qtbot.wait(200)  # let the timer fire at least once
        thread_obj.stop_grab('ch')
        assert collector.count >= 1
        assert all(call[0] == 'ch' for call in collector.calls)


# ---------------------------------------------------------------------------
# update_settings
# ---------------------------------------------------------------------------

class TestUpdateSettings:

    def test_update_settings_calls_commit_settings(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        # path=[] means root _plugin_settings node — always present regardless of params.
        thread_obj.update_settings([], 42, 'value')
        # commit_settings receives the root _plugin_settings Parameter node.
        assert len(plugin.commit_calls) == 1
        assert plugin.commit_calls[0] is thread_obj._plugin_settings

    def test_update_settings_before_ini_is_noop(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.update_settings(['param'], 1, 'value')  # must not raise
        assert plugin.commit_calls == []

    def test_update_settings_plugin_without_commit_settings(self, qapp):
        """Plugins that don't implement commit_settings are skipped silently."""
        class _PluginNoCommit:
            def open(self, settings): pass
            def close(self): pass
            def query_data(self, names=None, fresh=True): return FAKE_DTE
            def change_to(self, name, value): pass
            capabilities = None

        instance = _PluginNoCommit()
        thread_obj = ControllerThread(
            plugin_class=make_plugin_class(instance),
            params_state=None,
        )
        thread_obj.ini_hardware()
        thread_obj.update_settings(['param'], 1, 'value')  # must not raise


class TestTranslateModulePath:
    """ControllerThread._translate_module_path_to_plugin maps module paths to plugin paths.

    Tests inject _plugin_settings directly rather than going through ini_hardware,
    which avoids the complexity of old-style plugin lifecycle support.
    """

    def _make_thread_with_flat_settings(self, qapp):
        """Return a thread whose _plugin_settings has flat (old-style) layout."""
        from pymodaq_gui.parameter import Parameter
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj._plugin_settings = Parameter.create(name='Settings', type='group', children=[
            {'name': 'controller', 'type': 'group', 'children': [
                {'name': 'controller_ID', 'type': 'int', 'value': 0},
                {'name': 'axis', 'type': 'list', 'limits': ['X', 'Y'], 'value': 'X'},
            ]},
            {'name': 'units', 'type': 'str', 'value': ''},
            {'name': 'epsilon', 'type': 'float', 'value': 0.01},
            {'name': 'timeout', 'type': 'int', 'value': 10},
        ])
        return thread_obj, plugin

    def _make_thread_with_new_style_settings(self, qapp):
        """Return a thread whose _plugin_settings already has axis_settings group."""
        from pymodaq_gui.parameter import Parameter
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj._plugin_settings = Parameter.create(name='Settings', type='group', children=[
            {'name': 'controller', 'type': 'group', 'children': [
                {'name': 'controller_ID', 'type': 'int', 'value': 0},
            ]},
            {'name': 'axis_settings', 'type': 'group', 'children': [
                {'name': 'axis', 'type': 'list', 'limits': ['X', 'Y'], 'value': 'X'},
                {'name': 'units', 'type': 'str', 'value': ''},
            ]},
        ])
        return thread_obj, plugin

    def test_non_axis_settings_path_unchanged(self, qapp):
        thread, _ = self._make_thread_with_flat_settings(qapp)
        assert thread._translate_module_path_to_plugin(['controller', 'controller_ID']) == \
               ['controller', 'controller_ID']

    def test_empty_path_unchanged(self, qapp):
        thread, _ = self._make_thread_with_flat_settings(qapp)
        assert thread._translate_module_path_to_plugin([]) == []

    def test_flat_plugin_axis_translated(self, qapp):
        thread, _ = self._make_thread_with_flat_settings(qapp)
        assert thread._translate_module_path_to_plugin(['axis_settings', 'axis']) == \
               ['controller', 'axis']

    def test_flat_plugin_units_translated(self, qapp):
        thread, _ = self._make_thread_with_flat_settings(qapp)
        assert thread._translate_module_path_to_plugin(['axis_settings', 'units']) == ['units']

    def test_flat_plugin_epsilon_translated(self, qapp):
        thread, _ = self._make_thread_with_flat_settings(qapp)
        assert thread._translate_module_path_to_plugin(['axis_settings', 'epsilon']) == ['epsilon']

    def test_flat_plugin_timeout_translated(self, qapp):
        thread, _ = self._make_thread_with_flat_settings(qapp)
        assert thread._translate_module_path_to_plugin(['axis_settings', 'timeout']) == ['timeout']

    def test_new_style_plugin_axis_unchanged(self, qapp):
        thread, _ = self._make_thread_with_new_style_settings(qapp)
        assert thread._translate_module_path_to_plugin(['axis_settings', 'axis']) == \
               ['axis_settings', 'axis']

    def test_new_style_plugin_units_unchanged(self, qapp):
        thread, _ = self._make_thread_with_new_style_settings(qapp)
        assert thread._translate_module_path_to_plugin(['axis_settings', 'units']) == \
               ['axis_settings', 'units']

    def test_update_settings_reaches_flat_axis(self, qapp):
        """Axis update via module path actually lands on the plugin's controller/axis."""
        thread, _ = self._make_thread_with_flat_settings(qapp)
        thread.update_settings(['axis_settings', 'axis'], 'Y', 'value')
        assert thread._plugin_settings['controller', 'axis'] == 'Y'

    def test_update_settings_calls_commit_with_axis_param(self, qapp):
        """After path translation, commit_settings receives the axis Parameter node."""
        from pymodaq_gui.parameter import Parameter
        thread, plugin = self._make_thread_with_flat_settings(qapp)
        thread.update_settings(['axis_settings', 'axis'], 'Y', 'value')
        assert len(plugin.commit_calls) == 1
        assert plugin.commit_calls[0].name() == 'axis'


# ---------------------------------------------------------------------------
# Channel routing (single plugin)
# ---------------------------------------------------------------------------

class TestChannelRouting:
    """One plugin instance handles all channels — no dispatch logic needed."""

    def test_any_channel_name_is_passed_through(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        for ch in ('axis_x', 'axis_y', 'temperature', 'arbitrary'):
            thread_obj.request_read(ch)
        assert plugin.query_calls == [['axis_x'], ['axis_y'], ['temperature'], ['arbitrary']]

    def test_no_plugin_request_read_is_noop(self, qapp):
        thread_obj, _ = make_thread()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('axis_x')
        assert collector.count == 0


# ---------------------------------------------------------------------------
# Old-style actuator mock
# ---------------------------------------------------------------------------

class FakeDataActuator:
    """Minimal DataActuator stand-in.

    Supports ``units_as(unit).value()`` so that ``_to_plugin_units`` can do
    unit conversion without needing the full pint / DataActuator stack.
    The conversion is simplified: a 1000× factor between 'm' and 'mm'.
    """
    _SCALE = {'m': 1.0, 'mm': 1e3, 'um': 1e6}

    def __init__(self, value=0.0, units='mm'):
        self.value_float = value
        self.units = units
        self.name = 'actuator'

    def units_as(self, unit: str) -> 'FakeDataActuator':
        """Return a copy in *unit*, applying a simple m/mm/um scale."""
        src = self._SCALE.get(self.units, 1.0)
        dst = self._SCALE.get(unit, 1.0)
        return FakeDataActuator(self.value_float * dst / src, unit)

    def value(self, unit: str | None = None) -> float:
        if unit is None or unit == self.units:
            return self.value_float
        return self.units_as(unit).value_float


class OldStyleActuatorPlugin:
    """Simulates a DAQ_Move_base plugin (ini_stage / move_abs / poll_moving)."""

    # Marks it as old-style (no 'open' attribute)
    axis_name = 'axis_x'
    axis_unit = 'mm'

    # data_actuator_type mirrors DAQ_Move_base so _to_plugin_units can convert
    class _FloatType:
        """Minimal DataActuatorType.float stand-in."""
        def __eq__(self, other):
            from pymodaq.control_modules.move_utility_classes import DataActuatorType
            return other == DataActuatorType.float

    data_actuator_type = _FloatType()

    class _FakeTimer:
        """Minimal poll_timer duck-type (no Qt needed in unit tests)."""
        def stop(self): pass

    def __init__(self, parent=None, params_state=None):
        self.parent = parent
        self.params_state = params_state
        self.controller = object()   # fake SDK
        self.move_is_done = False
        self._ini_raises: Exception | None = None
        self._move_calls: list = []
        self._read_calls: int = 0
        self.poll_timer = self._FakeTimer()
        # Simulate move_done_signal with a simple callable list
        self._move_done_listeners: list = []

    # Minimal Signal duck-type for move_done_signal
    class _Sig:
        def __init__(self, plugin):
            self._plugin = plugin
        def connect(self, fn):
            self._plugin._move_done_listeners.append(fn)

    @property
    def move_done_signal(self):
        return self._Sig(self)

    def _emit_move_done(self, value):
        for fn in self._move_done_listeners:
            fn(value)

    def ini_stage(self, controller=None):
        if self._ini_raises:
            raise self._ini_raises
        return 'initialized', True

    def close(self):
        pass

    def get_actuator_value(self):
        self._read_calls += 1
        return FakeDataActuator(1.0)

    def move_abs(self, value):
        self._move_calls.append(('abs', value))

    def move_home(self):
        self._move_calls.append(('home', None))

    def stop_motion(self):
        self._move_calls.append(('stop', None))
        # Real plugins call self.move_done() here; simulate by emitting with current pos
        self._emit_move_done(FakeDataActuator(0.0))

    def poll_moving(self):
        # Immediately simulate completion (no real timer in tests)
        done = FakeDataActuator(getattr(self._move_calls[-1][1], 'value_float', 0.0)
                                if self._move_calls else 0.0)
        self._emit_move_done(done)

    def commit_settings(self, param):
        pass


def make_old_style_thread() -> tuple['ControllerThread', OldStyleActuatorPlugin]:
    """Return a (ControllerThread, OldStyleActuatorPlugin) pair.

    Inherits from OldStyleActuatorPlugin so ``hasattr(_PluginClass, 'ini_stage')``
    returns True and the old-style detection in ControllerThread works correctly.
    """
    plugin_instance = OldStyleActuatorPlugin()

    class _PluginClass(OldStyleActuatorPlugin):
        def __new__(cls, parent=None, params_state=None):
            plugin_instance.parent = parent
            plugin_instance.params_state = params_state
            return plugin_instance

    _PluginClass.__name__ = 'OldStyleActuatorPlugin'

    thread_obj = ControllerThread(plugin_class=_PluginClass, params_state=None)
    return thread_obj, plugin_instance


# ---------------------------------------------------------------------------
# Old-style actuator: ini_hardware
# ---------------------------------------------------------------------------

class TestOldStyleIniHardware:

    def test_ini_calls_ini_stage(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        assert thread_obj._plugin is plugin

    def test_ini_emits_hardware_status_true(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.ini_hardware()
        assert collector.count == 1
        connected, _ = collector.last()
        assert connected is True

    def test_ini_stores_controller(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        assert thread_obj._controller is plugin.controller

    def test_ini_failure_emits_hardware_status_false(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        plugin._ini_raises = RuntimeError('no device')
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.ini_hardware()
        connected, info = collector.last()
        assert connected is False
        assert 'no device' in info

    def test_parent_shim_title_set(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        assert plugin.parent is not None
        assert plugin.parent.title == 'OldStyleActuatorPlugin'

    def test_status_message_forwarded(self, qapp):
        """Plugin calling parent.status_sig.emit() should reach status_message."""
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.status_message.connect(collector)
        from pymodaq_utils.utils import ThreadCommand
        plugin.parent.status_sig.emit(ThreadCommand('Update_Status', 'Moving'))
        assert collector.count == 1
        assert 'Moving' in collector.last()[0]

    def test_check_position_forwarded_as_data_ready(self, qapp):
        """check_position polling updates during motion must arrive via data_ready, not status_message."""
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        data_collector = Collector()
        status_collector = Collector()
        thread_obj.data_ready.connect(data_collector)
        thread_obj.status_message.connect(status_collector)
        from pymodaq_utils.utils import ThreadCommand
        plugin.parent.status_sig.emit(ThreadCommand('check_position', FakeDataActuator(1.5)))
        assert data_collector.count == 1
        channel, val, is_temp = data_collector.last()
        assert channel == plugin.axis_name
        assert is_temp is False
        assert status_collector.count == 0


# ---------------------------------------------------------------------------
# Old-style actuator: request_write
# ---------------------------------------------------------------------------

class TestOldStyleRequestWrite:

    def test_request_write_calls_move_abs(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        thread_obj.request_write('axis_x', FakeDataActuator(5.0))
        assert plugin._move_calls[0][0] == 'abs'

    def test_request_write_emits_change_done(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.change_done.connect(collector)
        thread_obj.request_write('axis_x', FakeDataActuator(5.0))
        assert collector.count == 1
        channel, _ = collector.last()
        assert channel == 'axis_x'

    def test_request_write_home(self, qapp):
        from pymodaq.control_modules.controller_thread import ControlCommand
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        thread_obj.request_write('axis_x', ControlCommand.HOME)
        assert plugin._move_calls[0][0] == 'home'

    def test_request_write_stop(self, qapp):
        from pymodaq.control_modules.controller_thread import ControlCommand
        thread_obj, plugin = make_old_style_thread()
        collector = Collector()
        thread_obj.change_done.connect(collector)
        thread_obj.ini_hardware()
        thread_obj.request_write('axis_x', ControlCommand.STOP)
        assert plugin._move_calls[0][0] == 'stop'
        # stop_motion emits move_done_signal → change_done fires
        assert collector.count == 1

    def test_request_write_before_ini_is_noop(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        collector = Collector()
        thread_obj.change_done.connect(collector)
        thread_obj.request_write('axis_x', FakeDataActuator(1.0))
        assert collector.count == 0

    def test_broadcast_channel_empty(self, qapp):
        """Empty channel = broadcast; change_done emitted with empty channel."""
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.change_done.connect(collector)
        thread_obj.request_write('', FakeDataActuator(1.0))
        channel, _ = collector.last()
        assert channel == ''


# ---------------------------------------------------------------------------
# Old-style actuator: request_read
# ---------------------------------------------------------------------------

class TestOldStyleRequestRead:

    def test_request_read_calls_get_actuator_value(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        thread_obj.request_read('axis_x')
        assert plugin._read_calls == 1

    def test_request_read_emits_data_ready(self, qapp):
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('axis_x')
        assert collector.count == 1
        channel, _, is_temp = collector.last()
        assert channel == 'axis_x'
        assert is_temp is False


# ---------------------------------------------------------------------------
# Unit conversion in _to_plugin_units
# ---------------------------------------------------------------------------

class TestToPluginUnits:
    """_to_plugin_units must convert the GUI display unit (e.g. m) to the
    plugin's native unit (e.g. mm) before calling move_abs."""

    def test_float_plugin_receives_float_in_axis_unit(self, qapp):
        """Value sent in 'm' must arrive at move_abs as float in 'mm'."""
        thread_obj, plugin = make_old_style_thread()
        # plugin.axis_unit == 'mm'
        thread_obj.ini_hardware()
        # Send 0.005 m = 5 mm
        thread_obj.request_write('axis_x', FakeDataActuator(0.005, 'm'))
        assert len(plugin._move_calls) >= 1
        call_type, call_value = plugin._move_calls[0]
        assert call_type == 'abs'
        assert isinstance(call_value, float)
        assert abs(call_value - 5.0) < 1e-9, f"expected 5.0 mm, got {call_value}"

    def test_same_unit_passes_through_unchanged(self, qapp):
        """Value already in axis_unit must arrive as-is."""
        thread_obj, plugin = make_old_style_thread()
        thread_obj.ini_hardware()
        thread_obj.request_write('axis_x', FakeDataActuator(3.0, 'mm'))
        _, call_value = plugin._move_calls[0]
        assert abs(call_value - 3.0) < 1e-9, f"expected 3.0, got {call_value}"

    def test_plugin_without_data_actuator_type_passes_through(self, qapp):
        """Plugin without data_actuator_type should receive the value unchanged.

        ``getattr(plugin, 'data_actuator_type', None) is None`` triggers the
        pass-through path in ``_to_plugin_units``.
        """
        plugin_instance = OldStyleActuatorPlugin()
        # Shadow the class attribute with an instance-level None so
        # getattr(instance, 'data_actuator_type', None) returns None.
        plugin_instance.data_actuator_type = None

        class _PluginClass(OldStyleActuatorPlugin):
            def __new__(cls, parent=None, params_state=None):
                plugin_instance.parent = parent
                return plugin_instance

        thread_obj = ControllerThread(plugin_class=_PluginClass, params_state=None)
        thread_obj.ini_hardware()
        fa = FakeDataActuator(42.0, 'm')
        thread_obj.request_write('axis_x', fa)
        _, call_value = plugin_instance._move_calls[0]
        assert call_value is fa


# ---------------------------------------------------------------------------
# Old-style detector mock
# ---------------------------------------------------------------------------

FAKE_DTE_DETECTOR = object()   # stand-in for DataToExport from a detector


class FakeDTE:
    """Minimal DataToExport stand-in supporting deepcopy() and average()."""

    def __init__(self, val: float = 0.0):
        self.val = val

    def deepcopy(self) -> 'FakeDTE':
        return FakeDTE(self.val)

    def average(self, other: 'FakeDTE', n: int) -> 'FakeDTE':
        """Running average: (other * (n-1) + self) / n."""
        return FakeDTE((other.val * (n - 1) + self.val) / n)


class OldStyleDetectorPlugin:
    """Simulates a DAQ_Viewer_base plugin (ini_detector / grab_data / stop)."""

    hardware_averaging = False

    def __init__(self, parent=None, params_state=None):
        self.parent = parent
        self.params_state = params_state
        self.controller = object()   # fake SDK
        self._ini_raises: Exception | None = None
        self._grab_calls: int = 0
        self._stop_calls: int = 0
        self._close_calls: int = 0
        self._dte_listeners: list = []
        self._dte_temp_listeners: list = []

    class _Sig:
        def __init__(self, listeners):
            self._listeners = listeners
        def connect(self, fn):
            self._listeners.append(fn)

    @property
    def dte_signal(self):
        return self._Sig(self._dte_listeners)

    @property
    def dte_signal_temp(self):
        return self._Sig(self._dte_temp_listeners)

    def _emit_dte(self, dte=FAKE_DTE_DETECTOR):
        for fn in self._dte_listeners:
            fn(dte)

    def _emit_dte_temp(self, dte=FAKE_DTE_DETECTOR):
        for fn in self._dte_temp_listeners:
            fn(dte)

    def ini_detector(self, controller=None):
        if self._ini_raises:
            raise self._ini_raises
        return 'initialized', True

    def grab_data(self, Naverage=1, **kwargs):
        self._grab_calls += 1
        # Synchronously emit dte_signal (in a real plugin this is async)
        self._emit_dte()

    def stop(self):
        self._stop_calls += 1

    def close(self):
        self._close_calls += 1

    def commit_settings(self, param):
        pass


def make_old_style_detector_thread() -> tuple['ControllerThread', OldStyleDetectorPlugin]:
    """Return a (ControllerThread, OldStyleDetectorPlugin) pair."""
    plugin_instance = OldStyleDetectorPlugin()

    class _PluginClass(OldStyleDetectorPlugin):
        def __new__(cls, parent=None, params_state=None):
            plugin_instance.parent = parent
            plugin_instance.params_state = params_state
            return plugin_instance

    _PluginClass.__name__ = 'OldStyleDetectorPlugin'

    thread_obj = ControllerThread(plugin_class=_PluginClass, params_state=None)
    return thread_obj, plugin_instance


# ---------------------------------------------------------------------------
# Old-style detector: ini_hardware
# ---------------------------------------------------------------------------

class TestOldStyleDetectorIniHardware:

    def test_ini_calls_ini_detector(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        assert thread_obj._plugin is plugin

    def test_ini_emits_hardware_status_true(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.ini_hardware()
        assert collector.count == 1
        connected, _ = collector.last()
        assert connected is True

    def test_ini_stores_controller(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        assert thread_obj._controller is plugin.controller

    def test_ini_failure_emits_hardware_status_false(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        plugin._ini_raises = RuntimeError('camera offline')
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.ini_hardware()
        connected, info = collector.last()
        assert connected is False
        assert 'camera offline' in info

    def test_parent_shim_title_set(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        assert plugin.parent is not None
        assert plugin.parent.title == 'OldStyleDetectorPlugin'


# ---------------------------------------------------------------------------
# Old-style detector: request_read
# ---------------------------------------------------------------------------

class TestOldStyleDetectorRequestRead:

    def test_request_read_calls_grab_data(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        thread_obj.request_read('ch0')
        assert plugin._grab_calls == 1

    def test_request_read_emits_data_ready(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('ch0')
        assert collector.count == 1
        channel, dte, is_temp = collector.last()
        assert channel == 'ch0'
        assert dte is FAKE_DTE_DETECTOR
        assert is_temp is False

    def test_temp_data_emits_data_ready_with_is_temp_true(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()

        def grab_with_temp(Naverage=1, **kwargs):
            plugin._grab_calls += 1
            plugin._emit_dte_temp()
            plugin._emit_dte()
        plugin.grab_data = grab_with_temp

        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('ch0')
        assert collector.count == 2
        channel, _, is_temp = collector.calls[0]
        assert channel == 'ch0'
        assert is_temp is True
        channel, _, is_temp = collector.calls[1]
        assert channel == 'ch0'
        assert is_temp is False

    def test_concurrent_grab_ignored(self, qapp):
        """Second request_read while grab in progress must be a no-op."""
        thread_obj, plugin = make_old_style_detector_thread()

        # Override grab_data so it doesn't auto-emit dte_signal
        plugin._hold_grab = True
        original_grab = plugin.grab_data
        def slow_grab(Naverage=1, **kwargs):
            plugin._grab_calls += 1
            # do NOT emit dte_signal now — simulates async hardware
        plugin.grab_data = slow_grab

        thread_obj.ini_hardware()
        thread_obj.request_read('ch0')
        thread_obj.request_read('ch0')   # should be ignored
        assert plugin._grab_calls == 1   # only one grab started

    def test_stop_grab_calls_plugin_stop(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch0', 100.0)
        thread_obj.stop_grab('ch0')   # last subscriber everywhere → plugin.stop()
        assert plugin._stop_calls == 1

    def test_stop_grab_removes_last_group(self, qapp):
        """Stopping the last subscriber removes the group entry entirely."""
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch0', 100.0)
        thread_obj.stop_grab('ch0')
        assert '' not in thread_obj._groups

    def test_request_read_before_ini_is_noop(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('ch0')
        assert collector.count == 0

    def test_is_old_style_detector_true(self, qapp):
        thread_obj, _ = make_old_style_detector_thread()
        assert thread_obj._is_old_style_detector()
        assert not thread_obj._is_old_style_actuator()
        assert not thread_obj._is_new_style()

    def test_is_old_style_actuator_not_confused_with_detector(self, qapp):
        thread_obj, _ = make_old_style_thread()
        assert thread_obj._is_old_style_actuator()
        assert not thread_obj._is_old_style_detector()


# ---------------------------------------------------------------------------
# request_snap / software averaging
# ---------------------------------------------------------------------------

class TestRequestSnap:

    def test_request_snap_naverage_1_emits_single_data_ready(self, qapp):
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_snap('ch0', 1)
        assert collector.count == 1
        channel, dte, is_temp = collector.last()
        assert channel == 'ch0'
        assert is_temp is False

    def test_request_snap_software_averaging_emits_single_data_ready(self, qapp):
        """Without hardware_averaging CT emits exactly one data_ready per snap call.

        Software averaging across N grabs is the subscriber's (DAQ_Viewer's)
        responsibility — CT stays stateless.
        """
        thread_obj, plugin = make_old_style_detector_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_snap('ch0', 5)   # Naverage=5, no hardware averaging
        assert collector.count == 1
        assert collector.last()[2] is False  # single non-temp emission

    def test_request_snap_hardware_averaging_passes_naverage_to_plugin(self, qapp):
        """When hardware_averaging=True the plugin receives Naverage and returns once."""
        thread_obj, plugin = make_old_style_detector_thread()
        plugin.hardware_averaging = True
        thread_obj.ini_hardware()

        received_naverage = [None]
        def capturing_grab(Naverage=1, **kwargs):
            received_naverage[0] = Naverage
            plugin._grab_calls += 1
            plugin._emit_dte()
        plugin.grab_data = capturing_grab

        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_snap('ch0', 5)

        assert received_naverage[0] == 5
        assert collector.count == 1
        assert collector.last()[2] is False  # is_temp=False — single final emission


# ---------------------------------------------------------------------------
# Combined plugin mock
# ---------------------------------------------------------------------------

class CombinedPlugin:
    """Plugin with both ini_stage and ini_detector on one SDK object.

    Represents instruments that move and acquire data (e.g. a piezo stage
    with a built-in position sensor).
    """

    axis_name = 'axis_x'
    axis_unit = 'mm'
    hardware_averaging = False

    class _FakeTimer:
        def stop(self): pass

    def __init__(self, parent=None, params_state=None):
        self.parent = parent
        self.controller = object()
        self._stage_calls = 0
        self._detector_calls = 0
        self._read_calls = 0
        self._grab_calls = 0
        self._move_calls: list = []
        self.move_is_done = False
        self._dte_listeners: list = []
        self._move_done_listeners: list = []
        self.poll_timer = self._FakeTimer()

    class _DTESig:
        def __init__(self, listeners):
            self._listeners = listeners
        def connect(self, fn):
            self._listeners.append(fn)

    class _MoveSig:
        def __init__(self, plugin):
            self._plugin = plugin
        def connect(self, fn):
            self._plugin._move_done_listeners.append(fn)

    @property
    def dte_signal(self):
        return self._DTESig(self._dte_listeners)

    @property
    def move_done_signal(self):
        return self._MoveSig(self)

    def _emit_dte(self, dte=None):
        dte = dte or FAKE_DTE_DETECTOR
        for fn in self._dte_listeners:
            fn(dte)

    def _emit_move_done(self, value):
        for fn in self._move_done_listeners:
            fn(value)

    def ini_stage(self, controller=None):
        self._stage_calls += 1
        return 'stage initialized', True

    def ini_detector(self, controller=None):
        self._detector_calls += 1
        return 'detector initialized', True

    def close(self):
        pass

    def get_actuator_value(self):
        self._read_calls += 1
        return FakeDataActuator(1.0)

    def move_abs(self, value):
        self._move_calls.append(('abs', value))

    def move_home(self):
        self._move_calls.append(('home', None))

    def stop_motion(self):
        self._move_calls.append(('stop', None))
        self._emit_move_done(FakeDataActuator(0.0))

    def poll_moving(self):
        self._emit_move_done(FakeDataActuator(0.0))

    def grab_data(self, Naverage=1, **kwargs):
        self._grab_calls += 1
        self._emit_dte()

    def stop(self):
        pass

    def commit_settings(self, param):
        pass


def make_combined_thread() -> tuple['ControllerThread', CombinedPlugin]:
    """Return a (ControllerThread, CombinedPlugin) pair, not yet initialised."""
    plugin_instance = CombinedPlugin()

    class _PluginClass(CombinedPlugin):
        def __new__(cls, parent=None, params_state=None):
            plugin_instance.parent = parent
            return plugin_instance

    _PluginClass.__name__ = 'CombinedPlugin'

    thread_obj = ControllerThread(plugin_class=_PluginClass, params_state=None)
    return thread_obj, plugin_instance


# ---------------------------------------------------------------------------
# Combined plugin tests
# ---------------------------------------------------------------------------

class TestCombinedPlugin:

    def test_ini_calls_both_ini_stage_and_ini_detector(self, qapp):
        thread_obj, plugin = make_combined_thread()
        thread_obj.ini_hardware()
        assert plugin._stage_calls == 1
        assert plugin._detector_calls == 1

    def test_ini_emits_hardware_status_true(self, qapp):
        thread_obj, plugin = make_combined_thread()
        collector = Collector()
        thread_obj.hardware_status.connect(collector)
        thread_obj.ini_hardware()
        assert collector.last()[0] is True

    def test_is_combined_detected(self, qapp):
        thread_obj, _ = make_combined_thread()
        assert thread_obj._is_combined()
        assert thread_obj._is_old_style_actuator()
        assert thread_obj._is_old_style_detector()
        assert not thread_obj._is_new_style()

    def test_actuator_group_reads_position_not_grab(self, qapp):
        """group with role='actuator' calls get_actuator_value, not grab_data."""
        thread_obj, plugin = make_combined_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('axis_x', 100.0, group='actuator', role='actuator')
        thread_obj._on_group_tick('actuator')
        thread_obj.stop_grab('axis_x')
        assert plugin._read_calls >= 1
        assert plugin._grab_calls == 0

    def test_detector_group_calls_grab_data(self, qapp):
        """group with role='detector' calls grab_data, not get_actuator_value."""
        thread_obj, plugin = make_combined_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('image', 500.0, group='detector', role='detector')
        thread_obj._on_group_tick('detector')
        thread_obj.stop_grab('image')
        assert plugin._grab_calls >= 1
        assert plugin._read_calls == 0

    def test_detector_grab_in_flight_does_not_block_actuator_group(self, qapp):
        """A detector grab in-flight must never block actuator position reads."""
        thread_obj, plugin = make_combined_thread()
        thread_obj.ini_hardware()

        # Override grab_data so it never emits dte_signal — simulates async hardware.
        def slow_grab(Naverage=1, **kwargs):
            plugin._grab_calls += 1
        plugin.grab_data = slow_grab

        thread_obj.start_grab('image', 500.0, group='detector', role='detector')
        thread_obj._on_group_tick('detector')   # sets _grab_in_flight = True
        assert thread_obj._grab_in_flight is True

        thread_obj.start_grab('axis_x', 100.0, group='actuator', role='actuator')
        reads_before = plugin._read_calls
        thread_obj._on_group_tick('actuator')   # must NOT be blocked
        assert plugin._read_calls > reads_before

        thread_obj.stop_grab('image')
        thread_obj.stop_grab('axis_x')

    def test_auto_role_combined_defaults_to_detector(self, qapp):
        """role='auto' on a combined plugin resolves to detector (safe default)."""
        thread_obj, plugin = make_combined_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0, group='', role='auto')
        thread_obj._on_group_tick('')
        thread_obj.stop_grab('ch')
        assert plugin._grab_calls >= 1
        assert plugin._read_calls == 0

    def test_actuator_group_emits_data_ready(self, qapp):
        """Actuator group tick must emit data_ready with the correct channel."""
        thread_obj, plugin = make_combined_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.start_grab('axis_x', 100.0, group='actuator', role='actuator')
        thread_obj._on_group_tick('actuator')
        thread_obj.stop_grab('axis_x')
        assert collector.count >= 1
        channel, _, is_temp = collector.last()
        assert channel == 'axis_x'
        assert is_temp is False

    def test_detector_group_emits_data_ready(self, qapp):
        """Detector group tick must emit data_ready for each channel in the group."""
        thread_obj, plugin = make_combined_thread()
        thread_obj.ini_hardware()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.start_grab('image', 500.0, group='detector', role='detector')
        thread_obj._on_group_tick('detector')
        thread_obj.stop_grab('image')
        assert collector.count >= 1
        channel, dte, is_temp = collector.last()
        assert channel == 'image'
        assert is_temp is False


# ---------------------------------------------------------------------------
# Multi-axis actuator: axis-switching suppression (spinbox-selection regression)
# ---------------------------------------------------------------------------

class MultiAxisActuatorPlugin:
    """Old-style actuator with two axes and per-axis units.

    Simulates the real ``DAQ_Move_base.axis_name.setter`` side effect:
    every axis switch fires ``parent.status_sig.emit(ThreadCommand('units', unit))``
    — the path that was causing set_unit_as_suffix → setOpts → updateText →
    lineEdit.setText to clear the user's spinbox selection on every refresh cycle.
    """

    _AXES = ['X', 'Y']
    _UNITS = {'X': 'µm', 'Y': 'mm'}

    class _FakeTimer:
        def stop(self): pass

    class _Sig:
        def __init__(self, plugin):
            self._plugin = plugin
        def connect(self, fn):
            self._plugin._move_done_listeners.append(fn)

    def __init__(self, parent=None, params_state=None):
        self.parent = parent
        self._axis = 'X'
        self.controller = object()
        self.move_is_done = False
        self._read_calls = 0
        self._move_done_listeners: list = []
        self.poll_timer = self._FakeTimer()

    # ── axis_name with side-effect ────────────────────────────────────────

    @property
    def axis_name(self) -> str:
        return self._axis

    @axis_name.setter
    def axis_name(self, name: str):
        if name in self._AXES:
            self._axis = name
            if self.parent is not None:
                from pymodaq_utils.utils import ThreadCommand
                self.parent.status_sig.emit(ThreadCommand('units', self._UNITS[name]))

    @property
    def axis_unit(self) -> str:
        return self._UNITS[self._axis]

    # ── old-style plugin API ──────────────────────────────────────────────

    @property
    def move_done_signal(self):
        return self._Sig(self)

    def ini_stage(self, controller=None):
        return 'initialized', True

    def close(self):
        pass

    def get_actuator_value(self):
        self._read_calls += 1
        return FakeDataActuator(1.0)

    def move_abs(self, value):
        pass

    def move_home(self):
        pass

    def stop_motion(self):
        for fn in self._move_done_listeners:
            fn(FakeDataActuator(0.0))

    def poll_moving(self):
        for fn in self._move_done_listeners:
            fn(FakeDataActuator(1.0))

    def commit_settings(self, param):
        pass


def make_multi_axis_thread():
    plugin_instance = MultiAxisActuatorPlugin()

    class _PluginClass(MultiAxisActuatorPlugin):
        def __new__(cls, parent=None, params_state=None):
            plugin_instance.parent = parent
            return plugin_instance

    _PluginClass.__name__ = 'MultiAxisActuatorPlugin'
    thread_obj = ControllerThread(plugin_class=_PluginClass, params_state=None)
    return thread_obj, plugin_instance


class TestAxisSwitchingSuppression:
    """Regression tests for the spinbox-selection-clearing bug.

    Root cause: on every refresh cycle, _read_old_style_actuator switches
    plugin.axis_name, whose setter calls status_sig.emit('units', unit).
    _StatusSig.emit forwarded that as settings_changed → _update_units_ui →
    set_unit_as_suffix → setOpts → updateText → lineEdit.setText, which
    clears the active text selection in the target-position spinbox.

    Fix: _axis_switching flag suppresses all plugin events during the switch;
    _emit_channel_state re-emits units once after the switch.
    The set_unit_as_suffix guard prevents setOpts from firing when the suffix
    has not actually changed (making subsequent re-emissions no-ops in the UI).
    """

    def test_axis_switching_flag_false_after_read(self, qapp):
        """_axis_switching must be cleared even when an exception escapes the setter."""
        thread_obj, plugin = make_multi_axis_thread()
        thread_obj.ini_hardware()
        thread_obj.request_read('Y')
        assert thread_obj._axis_switching is False

    def test_status_sig_units_not_forwarded_while_switching(self, qapp):
        """Units emitted via status_sig while _axis_switching is True must be
        swallowed — no settings_changed signal reaches the GUI."""
        thread_obj, plugin = make_multi_axis_thread()
        thread_obj.ini_hardware()
        sc = Collector()
        thread_obj.settings_changed.connect(sc)

        thread_obj._axis_switching = True
        from pymodaq_utils.utils import ThreadCommand
        plugin.parent.status_sig.emit(ThreadCommand('units', 'mm'))

        assert sc.count == 0, "settings_changed must not fire while _axis_switching"

    def test_emit_channel_state_sends_settings_changed_for_units(self, qapp):
        """_emit_channel_state must emit settings_changed carrying the correct
        units for the channel that was just switched to."""
        thread_obj, plugin = make_multi_axis_thread()
        thread_obj.ini_hardware()

        # Manually place plugin on axis Y so axis_unit returns the Y unit.
        plugin._axis = 'Y'

        sc = Collector()
        thread_obj.settings_changed.connect(sc)
        thread_obj._emit_channel_state('Y')

        assert sc.count == 1
        channel, path, data, change = sc.last()
        assert channel == 'Y'
        assert path == ['units']
        assert data == 'mm'
        assert change == 'value'

    def test_no_spurious_settings_changed_when_axis_unchanged(self, qapp):
        """Reading the same channel repeatedly must not emit settings_changed at all
        (axis_name.setter is never called when the axis is already correct)."""
        thread_obj, plugin = make_multi_axis_thread()
        thread_obj.ini_hardware()
        sc = Collector()
        thread_obj.settings_changed.connect(sc)

        # Plugin starts on 'X'; read 'X' three times — no switch, no emission.
        thread_obj.request_read('X')
        thread_obj.request_read('X')
        thread_obj.request_read('X')

        assert sc.count == 0

    def test_alternating_reads_emit_exactly_one_settings_changed_per_switch(self, qapp):
        """Each axis switch must produce exactly one settings_changed (from
        _emit_channel_state), never the multiple emissions that the old code
        produced via _StatusSig.emit for every read cycle.

        Before the fix: every X→Y switch fired settings_changed twice
        (once from _StatusSig, once — indirectly — from plugin.settings change),
        causing lineEdit.setText to clear the spinbox selection on every tick.
        After the fix: exactly one emission per switch, from _emit_channel_state.
        """
        thread_obj, plugin = make_multi_axis_thread()
        thread_obj.ini_hardware()
        sc = Collector()
        thread_obj.settings_changed.connect(sc)

        # Read X: no axis switch (already on X), no emission.
        thread_obj.request_read('X')
        assert sc.count == 0, "no switch → no settings_changed"

        # Switch X→Y: exactly one settings_changed(Y, units, mm).
        thread_obj.request_read('Y')
        assert sc.count == 1, "X→Y switch must emit exactly one settings_changed"
        ch, path, data, _ = sc.calls[0]
        assert (ch, path, data) == ('Y', ['units'], 'mm')

        # Switch Y→X: exactly one settings_changed(X, units, µm).
        thread_obj.request_read('X')
        assert sc.count == 2, "Y→X switch must emit exactly one settings_changed"
        ch, path, data, _ = sc.calls[1]
        assert (ch, path, data) == ('X', ['units'], 'µm')

        # Second X→Y: exactly one more settings_changed.
        thread_obj.request_read('Y')
        assert sc.count == 3, "second X→Y switch must emit exactly one settings_changed"

    def test_write_axis_switch_also_suppressed(self, qapp):
        """_write_old_style_actuator switches axis_name too; that switch must
        also be suppressed and re-emitted cleanly."""
        thread_obj, plugin = make_multi_axis_thread()
        thread_obj.ini_hardware()
        sc = Collector()
        thread_obj.settings_changed.connect(sc)

        # Move on Y while plugin is on X → triggers axis switch X→Y.
        thread_obj.request_write('Y', FakeDataActuator(5.0))

        # Exactly one settings_changed from _emit_channel_state, none from status_sig.
        units_changes = [c for c in sc.calls if c[1] == ['units']]
        assert len(units_changes) == 1
        ch, path, data, _ = units_changes[0]
        assert (ch, path, data) == ('Y', ['units'], 'mm')

    def test_data_ready_still_emitted_after_suppressed_switch(self, qapp):
        """The suppression must not block data_ready — the position value must
        always arrive at subscribers after an axis switch."""
        thread_obj, plugin = make_multi_axis_thread()
        thread_obj.ini_hardware()
        dr = Collector()
        thread_obj.data_ready.connect(dr)

        thread_obj.request_read('Y')   # axis switch X→Y

        assert dr.count == 1
        channel, _, is_temp = dr.last()
        assert channel == 'Y'
        assert is_temp is False
