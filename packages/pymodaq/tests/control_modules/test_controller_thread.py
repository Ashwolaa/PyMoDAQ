"""Tests for ControllerThread (Phase CT-2).

Design: one physical hardware device → one ControllerThread → one plugin instance.
DAQ_Move and DAQ_Viewer are pure GUI subscribers; they never touch the SDK.

All tests use new-style mock plugins only (open / close / query_data / change_to).
Old-style adapter wiring (DAQ_Move_base / DAQ_Viewer_base) is covered in Phase 4.

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

    def commit_settings(self, path, data, change) -> None:
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
    """Return a (ControllerThread, MockPlugin) pair, not yet initialised."""
    if plugin_instance is None:
        plugin_instance = MockPlugin()
    plugin_cls = make_plugin_class(plugin_instance)
    thread_obj = ControllerThread(plugin_class=plugin_cls, settings=FakeSettings())
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

    def test_ini_passes_settings_to_open(self, qapp):
        thread_obj, plugin = make_thread()
        thread_obj.ini_hardware()
        assert isinstance(plugin.open_called_with, FakeSettings)

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
        assert 'ch' in thread_obj._grab_timers
        thread_obj.close_hardware()
        assert thread_obj._grab_timers == {}


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
        channel, dte = collector.last()
        assert channel == 'axis_x'
        assert dte is FAKE_DTE

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
# update_settings
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
            def open(self, settings): pass
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
