"""Tests for pymodaq.control_modules.hardware_worker.

All tests in this file are headless (no Qt backend required) except those
in classes marked with ``pytestmark = pytest.mark.qt``.  The Qt-dependent
tests (grab loop timers) are skipped automatically when no Qt backend is
available.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch
import pytest

try:
    from qtpy.QtCore import QObject, QCoreApplication, QTimer
    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False

from pymodaq.control_modules.hardware_worker import _is_new_style, DAQ_HardwareWorker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plugin(new_style: bool = True, query_returns=None):
    """Return a mock plugin with the given _new_style_plugin flag."""
    plugin = MagicMock()
    plugin._new_style_plugin = new_style
    if query_returns is not None:
        plugin.query_data.return_value = query_returns
    return plugin


def _make_dte(value: float = 0.0):
    """Build a minimal DataToExport with one scalar DataActuator."""
    import numpy as np
    from pymodaq_data.data import DataToExport
    from pymodaq.utils.data import DataActuator
    dwa = DataActuator('ch', data=np.array([value]))
    return DataToExport(name='test', data=[dwa])


# ---------------------------------------------------------------------------
# _is_new_style
# ---------------------------------------------------------------------------

class TestIsNewStyle:
    def test_true_when_flag_true(self):
        plugin = MagicMock()
        plugin._new_style_plugin = True
        assert _is_new_style(plugin) is True

    def test_false_when_flag_false(self):
        plugin = MagicMock()
        plugin._new_style_plugin = False
        assert _is_new_style(plugin) is False

    def test_false_when_flag_missing(self):
        class NoFlag:
            pass
        assert _is_new_style(NoFlag()) is False

    def test_false_for_non_plugin_object(self):
        assert _is_new_style(42) is False
        assert _is_new_style(None) is False


# ---------------------------------------------------------------------------
# DAQ_HardwareWorker — construction (Qt required)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _QT_AVAILABLE, reason="Qt not available")
class TestDAQHardwareWorkerConstruction:
    @pytest.fixture(autouse=True)
    def app(self, qapp):
        return qapp

    def test_creates_without_error(self):
        plugin = _make_plugin()
        worker = DAQ_HardwareWorker(plugin)
        assert worker is not None
        worker.close()

    def test_has_data_ready_signal(self):
        plugin = _make_plugin()
        worker = DAQ_HardwareWorker(plugin)
        assert hasattr(worker, 'data_ready_signal')
        worker.close()

    def test_has_change_done_signal(self):
        plugin = _make_plugin()
        worker = DAQ_HardwareWorker(plugin)
        assert hasattr(worker, 'change_done_signal')
        worker.close()

    def test_grabbed_names_empty_at_start(self):
        plugin = _make_plugin()
        worker = DAQ_HardwareWorker(plugin)
        assert worker.grabbed_names == set()
        worker.close()


# ---------------------------------------------------------------------------
# snap
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _QT_AVAILABLE, reason="Qt not available")
class TestSnap:
    @pytest.fixture(autouse=True)
    def app(self, qapp):
        return qapp

    def test_snap_calls_query_data_once(self):
        dte = _make_dte(1.0)
        plugin = _make_plugin(query_returns=dte)
        worker = DAQ_HardwareWorker(plugin)

        worker.snap('ch')

        plugin.query_data.assert_called_once_with(names=['ch'], fresh=True)
        worker.close()

    def test_snap_emits_data_ready_signal(self):
        dte = _make_dte(1.0)
        plugin = _make_plugin(query_returns=dte)
        worker = DAQ_HardwareWorker(plugin)

        received = []
        worker.data_ready_signal.connect(lambda n, d: received.append((n, d)))
        worker.snap('ch')

        assert len(received) == 1
        assert received[0][0] == 'ch'
        assert received[0][1] is dte
        worker.close()

    def test_snap_updates_cache(self):
        dte = _make_dte(5.0)
        plugin = _make_plugin(query_returns=dte)
        worker = DAQ_HardwareWorker(plugin)

        worker.snap('ch')

        assert worker.get_cached('ch') is dte
        worker.close()


# ---------------------------------------------------------------------------
# get_cached
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _QT_AVAILABLE, reason="Qt not available")
class TestGetCached:
    @pytest.fixture(autouse=True)
    def app(self, qapp):
        return qapp

    def test_returns_none_before_any_snap(self):
        plugin = _make_plugin()
        worker = DAQ_HardwareWorker(plugin)
        assert worker.get_cached('unknown') is None
        worker.close()

    def test_returns_last_value_without_query_data_call(self):
        dte = _make_dte(3.0)
        plugin = _make_plugin(query_returns=dte)
        worker = DAQ_HardwareWorker(plugin)

        worker.snap('ch')
        plugin.query_data.reset_mock()

        result = worker.get_cached('ch')

        plugin.query_data.assert_not_called()
        assert result is dte
        worker.close()


# ---------------------------------------------------------------------------
# change_to
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _QT_AVAILABLE, reason="Qt not available")
class TestChangeTo:
    @pytest.fixture(autouse=True)
    def app(self, qapp):
        return qapp

    def test_delegates_to_plugin(self):
        plugin = _make_plugin()
        worker = DAQ_HardwareWorker(plugin)

        worker.change_to('axis', 42.0)

        plugin.change_to.assert_called_once_with('axis', 42.0)
        worker.close()


# ---------------------------------------------------------------------------
# change_done_signal relay
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _QT_AVAILABLE, reason="Qt not available")
class TestChangeDoneRelay:
    @pytest.fixture(autouse=True)
    def app(self, qapp):
        return qapp

    def test_change_done_signal_relayed_from_plugin(self):
        plugin = _make_plugin()
        worker = DAQ_HardwareWorker(plugin)

        # The relay is set up via plugin.change_done_signal.connect(worker.change_done_signal)
        # Verify connect was called during construction
        plugin.change_done_signal.connect.assert_called_once_with(worker.change_done_signal)
        worker.close()


# ---------------------------------------------------------------------------
# grab / stop (require Qt event loop)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _QT_AVAILABLE, reason="Qt not available")
class TestGrabStop:
    @pytest.fixture(autouse=True)
    def app(self, qapp):
        return qapp

    def test_grab_adds_to_grabbed_names(self):
        plugin = _make_plugin(query_returns=_make_dte())
        worker = DAQ_HardwareWorker(plugin, grab_period_ms=50)

        worker.grab('ch')
        assert 'ch' in worker.grabbed_names
        worker.close()

    def test_stop_removes_from_grabbed_names(self):
        plugin = _make_plugin(query_returns=_make_dte())
        worker = DAQ_HardwareWorker(plugin, grab_period_ms=50)

        worker.grab('ch')
        worker.stop('ch')
        assert 'ch' not in worker.grabbed_names
        worker.close()

    def test_grab_noop_if_already_grabbing(self):
        plugin = _make_plugin(query_returns=_make_dte())
        worker = DAQ_HardwareWorker(plugin, grab_period_ms=50)

        worker.grab('ch')
        worker.grab('ch')  # second call is a no-op
        assert len(worker._grab_timers) == 1
        worker.close()

    def test_stop_noop_if_not_grabbing(self):
        plugin = _make_plugin()
        worker = DAQ_HardwareWorker(plugin)

        worker.stop('nonexistent')  # should not raise
        worker.close()

    def test_grab_emits_data_ready_on_tick(self, qtbot):
        dte = _make_dte(7.0)
        plugin = _make_plugin(query_returns=dte)
        worker = DAQ_HardwareWorker(plugin, grab_period_ms=30)

        received = []
        worker.data_ready_signal.connect(lambda n, d: received.append((n, d)))

        worker.grab('ch')
        qtbot.waitUntil(lambda: len(received) >= 1, timeout=500)
        worker.close()

        assert received[0][0] == 'ch'
        assert received[0][1] is dte

    def test_stop_halts_grab_loop(self, qtbot):
        dte = _make_dte()
        plugin = _make_plugin(query_returns=dte)
        worker = DAQ_HardwareWorker(plugin, grab_period_ms=20)

        received = []
        worker.data_ready_signal.connect(lambda n, d: received.append((n, d)))

        worker.grab('ch')
        qtbot.waitUntil(lambda: len(received) >= 1, timeout=300)
        worker.stop('ch')
        count_after_stop = len(received)

        # Wait to confirm no more ticks arrive
        QTimer.singleShot(100, lambda: None)
        qtbot.wait(120)
        assert len(received) == count_after_stop
        worker.close()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _QT_AVAILABLE, reason="Qt not available")
class TestClose:
    @pytest.fixture(autouse=True)
    def app(self, qapp):
        return qapp

    def test_close_stops_all_grab_loops(self):
        plugin = _make_plugin(query_returns=_make_dte())
        worker = DAQ_HardwareWorker(plugin, grab_period_ms=50)

        worker.grab('a')
        worker.grab('b')
        assert len(worker.grabbed_names) == 2

        worker.close()
        assert len(worker.grabbed_names) == 0

    def test_close_clears_cache(self):
        dte = _make_dte()
        plugin = _make_plugin(query_returns=dte)
        worker = DAQ_HardwareWorker(plugin)

        worker.snap('ch')
        assert worker.get_cached('ch') is dte

        worker.close()
        assert worker.get_cached('ch') is None


# ---------------------------------------------------------------------------
# Old-style routing (no DAQ_HardwareWorker used)
# ---------------------------------------------------------------------------

class TestOldStyleRouting:
    """_is_new_style returns False for DAQ_Move_base / DAQ_Viewer_base adapters."""

    def test_daq_move_base_is_not_new_style(self):
        """DAQ_Move_base sets _new_style_plugin = False."""
        from pymodaq.control_modules.move_utility_classes import DAQ_Move_base
        assert DAQ_Move_base._new_style_plugin is False

    def test_daq_viewer_base_is_not_new_style(self):
        """DAQ_Viewer_base sets _new_style_plugin = False."""
        from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base
        assert DAQ_Viewer_base._new_style_plugin is False

    def test_is_new_style_false_for_move_base_instance(self):
        plugin = MagicMock()
        plugin._new_style_plugin = False
        assert _is_new_style(plugin) is False
