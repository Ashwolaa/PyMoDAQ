"""Tests for ControllerThread (Phase CT-2).

All tests use new-style mock plugins only (query_data / change_to interface).
Old-style adapter wiring (DAQ_Move_base / DAQ_Viewer_base) is covered in Phase 4.

Qt is required (ControllerThread is a QObject), but no GUI is shown.
Slots are called directly in the test thread — no QThread / event loop needed
for the core logic tests.  Timer firing is verified with qtbot.
"""
from __future__ import annotations

import pytest
from qtpy.QtCore import QCoreApplication

from pymodaq.control_modules.controller_thread import ControllerThread


# ---------------------------------------------------------------------------
# Mock plugin helpers
# ---------------------------------------------------------------------------

FAKE_DTE = object()   # stand-in for DataToExport


class MockPlugin:
    """New-style plugin stub: records every call, raises on demand."""

    def __init__(self):
        self.open_called_with = None   # (settings, controller)
        self.close_called = False
        self.query_calls: list = []    # list of names lists
        self.change_calls: list = []   # list of (name, value)
        self.commit_calls: list = []   # list of (path, data, change)

        self._open_raises: Exception | None = None
        self._query_raises: Exception | None = None
        self._change_raises: Exception | None = None
        self._controller_obj = object()   # fake SDK object returned by open()
        self._capabilities = None

    # ── plugin interface ─────────────────────────────────────────────────────

    def open(self, settings, controller=None):
        self.open_called_with = (settings, controller)
        if self._open_raises:
            raise self._open_raises
        return self._controller_obj

    def close(self):
        self.close_called = True

    def query_data(self, names=None, fresh=True):
        self.query_calls.append(names)
        if self._query_raises:
            raise self._query_raises
        return FAKE_DTE

    def change_to(self, name, value):
        self.change_calls.append((name, value))
        if self._change_raises:
            raise self._change_raises

    def commit_settings(self, path, data, change):
        self.commit_calls.append((path, data, change))

    @property
    def capabilities(self):
        return self._capabilities


class FakeSettings:
    """Stand-in for pymodaq_gui Parameter."""
    pass


def make_plugin_class(plugin_instance: MockPlugin) -> type:
    """Return a plugin class whose constructor always returns *plugin_instance*."""
    instance = plugin_instance

    class _PluginClass:
        def __new__(cls):
            return instance

    _PluginClass.__name__ = 'MockPluginClass'
    return _PluginClass


def make_thread(plugin_instance: MockPlugin | None = None) -> tuple[ControllerThread, MockPlugin]:
    """Return a ControllerThread + its MockPlugin, not yet initialised."""
    if plugin_instance is None:
        plugin_instance = MockPlugin()
    plugin_cls = make_plugin_class(plugin_instance)
    settings = FakeSettings()
    thread_obj = ControllerThread(plugin_class=plugin_cls, settings=settings)
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
# ini_hardware tests
# ---------------------------------------------------------------------------

class TestIniHardware:

    def test_ini_calls_plugin_open(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        assert plugin.open_called_with is not None

    def test_ini_passes_settings_to_open(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        settings_passed, _ = plugin.open_called_with
        assert isinstance(settings_passed, FakeSettings)

    def test_ini_stores_controller_from_open(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        assert thread_obj._controller is plugin._controller_obj

    def test_ini_stores_plugin_instance(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        assert plugin in thread_obj._plugins.values()

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
        plugin._capabilities = None
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
        assert collector.count == 1
        connected, info = collector.last()
        assert connected is False
        assert 'device not found' in info

    def test_second_ini_passes_existing_controller(self, qapp):
        """Second plugin class gets the already-open controller passed in."""
        plugin_a = MockPlugin()
        plugin_b = MockPlugin()
        cls_a = make_plugin_class(plugin_a)
        cls_b = make_plugin_class(plugin_b)
        settings = FakeSettings()

        # First plugin opens hardware
        thread_obj = ControllerThread(plugin_class=cls_a, settings=settings)
        thread_obj.ini_hardware()
        sdk_obj = plugin_a._controller_obj

        # Second plugin class arrives — simulate by swapping _plugin_class
        thread_obj._plugin_class = cls_b
        thread_obj.ini_hardware()

        _, controller_received = plugin_b.open_called_with
        assert controller_received is sdk_obj


# ---------------------------------------------------------------------------
# close_hardware tests
# ---------------------------------------------------------------------------

class TestCloseHardware:

    def test_close_calls_plugin_close(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.close_hardware()
        assert plugin.close_called

    def test_close_clears_plugins(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.close_hardware()
        assert thread_obj._plugins == {}

    def test_close_clears_controller(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.close_hardware()
        assert thread_obj._controller is None

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
        assert 'ch' in thread_obj._grab_timers
        thread_obj.close_hardware()
        assert thread_obj._grab_timers == {}


# ---------------------------------------------------------------------------
# request_read tests
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
        channel, dte = collector.last()
        assert channel == 'axis_x'
        assert dte is FAKE_DTE

    def test_request_read_before_ini_is_noop(self, qapp):
        thread_obj, plugin = make_thread()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('axis_x')  # no plugin yet
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
# request_write tests
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
# start_grab / stop_grab tests
# ---------------------------------------------------------------------------

class TestGrabTimers:

    def test_start_grab_creates_timer(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0)
        assert 'ch' in thread_obj._grab_timers
        thread_obj.stop_grab('ch')

    def test_stop_grab_removes_timer(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0)
        thread_obj.stop_grab('ch')
        assert 'ch' not in thread_obj._grab_timers

    def test_stop_grab_unknown_channel_is_noop(self, qapp):
        thread_obj, _ = make_thread()
        thread_obj.stop_grab('nonexistent')  # must not raise

    def test_start_grab_replaces_existing_timer(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.start_grab('ch', 100.0)
        timer_first = thread_obj._grab_timers['ch']
        thread_obj.start_grab('ch', 200.0)
        timer_second = thread_obj._grab_timers['ch']
        assert timer_first is not timer_second
        assert timer_second.interval() == 200
        thread_obj.stop_grab('ch')

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
# update_settings tests
# ---------------------------------------------------------------------------

class TestUpdateSettings:

    def test_update_settings_calls_commit_settings(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.update_settings(['param', 'value'], 42, 'value')
        assert plugin.commit_calls == [(['param', 'value'], 42, 'value')]

    def test_update_settings_before_ini_is_noop(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.update_settings(['param'], 1, 'value')  # must not raise
        assert plugin.commit_calls == []

    def test_update_settings_plugin_without_commit_settings(self, qapp):
        """Plugins that don't implement commit_settings are skipped silently."""
        class _PluginNoCommit:
            """Minimal plugin with no commit_settings method."""
            def open(self, settings, controller=None): return None
            def close(self): pass
            def query_data(self, names=None, fresh=True): return FAKE_DTE
            def change_to(self, name, value): pass
            capabilities = None

        instance = _PluginNoCommit()
        thread_obj = ControllerThread(
            plugin_class=make_plugin_class(instance),
            settings=FakeSettings(),
        )
        thread_obj.ini_hardware()
        thread_obj.update_settings(['param'], 1, 'value')  # must not raise


# ---------------------------------------------------------------------------
# Multi-plugin channel dispatch tests
# ---------------------------------------------------------------------------

class TestChannelDispatch:

    def test_single_plugin_handles_any_channel(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        thread_obj.request_read('any_channel')
        assert plugin.query_calls == [['any_channel']]

    def test_multi_plugin_dispatches_by_capabilities(self, qapp):
        """With two plugins, request_read dispatches to the one whose
        Capabilities include the requested channel."""

        class FakeCaps:
            def __init__(self, var_names, obs_names):
                self.variables = [type('V', (), {'name': n})() for n in var_names]
                self.observables = [type('O', (), {'name': n})() for n in obs_names]

        plugin_move = MockPlugin()
        plugin_move._capabilities = FakeCaps(['axis_x'], [])

        plugin_view = MockPlugin()
        plugin_view._capabilities = FakeCaps([], ['temperature'])

        settings = FakeSettings()
        thread_obj = ControllerThread(
            plugin_class=make_plugin_class(plugin_move),
            settings=settings,
        )
        cls_move = make_plugin_class(plugin_move)
        cls_view = make_plugin_class(plugin_view)
        # Manually inject both plugins (simulates two ini_hardware calls)
        thread_obj._plugins[cls_move] = plugin_move
        thread_obj._plugins[cls_view] = plugin_view

        thread_obj.request_read('axis_x')
        assert plugin_move.query_calls == [['axis_x']]
        assert plugin_view.query_calls == []

        thread_obj.request_read('temperature')
        assert plugin_view.query_calls == [['temperature']]
        assert plugin_move.query_calls == [['axis_x']]  # unchanged

    def test_no_plugins_request_read_is_noop(self, qapp):
        thread_obj, _ = make_thread()
        collector = Collector()
        thread_obj.data_ready.connect(collector)
        thread_obj.request_read('axis_x')
        assert collector.count == 0
