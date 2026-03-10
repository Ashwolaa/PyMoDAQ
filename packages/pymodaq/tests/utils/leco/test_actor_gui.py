"""Tests for actor_gui.py.

Headless tests (no display needed)
-----------------------------------
- get_hardware_registry  (mocked entry points)
- ActorWorker.init_instrument  (merged: instantiate + connect + listen)
- ActorWorker.stop_actor

Qt-dependent tests (require qtbot from pytest-qt)
--------------------------------------------------
- PymodaqActorGUI instrument param limits
- PymodaqActorGUI._populate_caps_tree + action buttons
- PymodaqActorGUI._on_status for ACTOR_READY / ACTOR_STOPPED / ERROR

All Qt-dependent tests are guarded so the suite passes on headless CI.
"""
from __future__ import annotations

import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from pymodaq_utils.utils import ThreadCommand


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_plugin_class():
    """Minimal hardware class implementing the actor device interface."""

    class _MockPlugin:
        capabilities = None

        def __init__(self):
            pass

        def connect(self): pass
        def close(self): pass
        def read(self, names=None): return MagicMock()
        def write(self, name, value): pass

    return _MockPlugin


def _make_registry_entry(name, cls, caps=None):
    from pymodaq.control_modules.capabilities import Capabilities
    return {'name': name, 'cls': cls, 'capabilities': caps or Capabilities()}


# ── TestHardwareRegistry ───────────────────────────────────────────────────────

class TestHardwareRegistry:
    def test_empty_when_no_entry_points(self):
        from pymodaq.utils.leco.hardware_registry import get_hardware_registry
        with patch('pymodaq.utils.leco.hardware_registry.entry_points', return_value=[]):
            result = get_hardware_registry()
        assert result == []

    def test_returns_name_cls_capabilities(self, mock_plugin_class):
        from pymodaq.control_modules.capabilities import Capabilities, ContinuousVariable
        from pymodaq.utils.leco.hardware_registry import get_hardware_registry

        mock_plugin_class.capabilities = Capabilities(
            variables=[ContinuousVariable('pos', units='mm', lo=-1, hi=1, epsilon=0.001)]
        )

        ep = MagicMock()
        ep.name = 'MockStage'
        ep.load.return_value = mock_plugin_class

        with patch('pymodaq.utils.leco.hardware_registry.entry_points', return_value=[ep]):
            result = get_hardware_registry()

        assert len(result) == 1
        assert result[0]['name'] == 'MockStage'
        assert result[0]['cls'] is mock_plugin_class
        assert isinstance(result[0]['capabilities'], Capabilities)

    def test_bad_entry_point_is_skipped(self):
        from pymodaq.utils.leco.hardware_registry import get_hardware_registry

        ep = MagicMock()
        ep.name = 'BadPlugin'
        ep.load.side_effect = ImportError('no module')

        with patch('pymodaq.utils.leco.hardware_registry.entry_points', return_value=[ep]):
            result = get_hardware_registry()

        assert result == []

    def test_infers_capabilities_when_absent(self, mock_plugin_class):
        from pymodaq.control_modules.capabilities import Capabilities
        from pymodaq.utils.leco.hardware_registry import get_hardware_registry

        mock_plugin_class.capabilities = None

        ep = MagicMock()
        ep.name = 'NoCaps'
        ep.load.return_value = mock_plugin_class

        fake_caps = Capabilities()
        with patch('pymodaq.utils.leco.hardware_registry.entry_points', return_value=[ep]):
            # infer_capabilities is imported inside get_hardware_registry; patch the source
            with patch('pymodaq.control_modules.capabilities.infer_capabilities',
                       return_value=fake_caps):
                result = get_hardware_registry()

        assert result[0]['capabilities'] is fake_caps


# ── ActorWorker ────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def qapp_core():
    from qtpy.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    return app


@pytest.fixture()
def worker(qapp_core):
    from pymodaq.utils.leco.actor_gui import ActorWorker
    return ActorWorker()


class TestActorWorkerInit:
    def test_success_emits_actor_ready(self, worker, mock_plugin_class):
        received = []
        worker.status_sig.connect(received.append)

        class _FakeActor:
            def __init__(self, **kwargs): pass
            def connect(self): pass
            def listen(self, stop_event=None): stop_event.wait()
            def get_capabilities(self): return {'observables': [], 'variables': []}
            def disconnect(self): pass

        with patch('pymodaq.utils.leco.actor_gui.PymodaqActor', _FakeActor):
            worker.init_instrument(mock_plugin_class, 'myactor', 'localhost', 12300)

        assert received[0].command == 'ACTOR_READY'
        assert worker._actor_thread is not None and worker._actor_thread.is_alive()
        worker.stop_actor()

    def test_instantiates_device_class(self, worker, mock_plugin_class):
        """init_instrument must pass the class to PymodaqActor (not an instance)."""
        captured = {}

        class _CapturingActor:
            def __init__(self, name, device_class, host, port):
                captured['device_class'] = device_class
            def connect(self): pass
            def listen(self, stop_event=None): stop_event.wait()
            def get_capabilities(self): return {'observables': [], 'variables': []}
            def disconnect(self): pass

        with patch('pymodaq.utils.leco.actor_gui.PymodaqActor', _CapturingActor):
            worker.init_instrument(mock_plugin_class, 'myactor', 'localhost', 12300)

        assert captured['device_class'] is mock_plugin_class
        worker.stop_actor()

    def test_connect_failure_emits_error(self, worker, mock_plugin_class):
        received = []
        worker.status_sig.connect(received.append)

        mock_actor = MagicMock()
        mock_actor.connect.side_effect = ConnectionError('coordinator not found')

        with patch('pymodaq.utils.leco.actor_gui.PymodaqActor', return_value=mock_actor):
            worker.init_instrument(mock_plugin_class, 'myactor', 'localhost', 12300)

        assert received[0].command == 'ERROR'
        assert 'coordinator not found' in received[0].attribute
        assert worker._actor is None

    def test_ini_stage_not_called(self, worker):
        """The worker must not call ini_stage — that is the director's job."""
        ini_called = []

        class _Plugin:
            def ini_stage(self): ini_called.append(True)

        mock_actor = MagicMock()
        mock_actor.get_capabilities.return_value = {'observables': [], 'variables': []}

        with patch('pymodaq.utils.leco.actor_gui.PymodaqActor', return_value=mock_actor):
            worker.init_instrument(_Plugin, 'a', 'localhost', 12300)

        assert ini_called == []
        worker.stop_actor()


class TestActorWorkerStop:
    def test_stop_emits_actor_stopped(self, worker, mock_plugin_class):
        mock_actor = MagicMock()
        mock_actor.get_capabilities.return_value = {'observables': [], 'variables': []}

        with patch('pymodaq.utils.leco.actor_gui.PymodaqActor', return_value=mock_actor):
            worker.init_instrument(mock_plugin_class, 'myactor', 'localhost', 12300)

        received = []
        worker.status_sig.connect(received.append)
        worker.stop_actor()

        assert received[0].command == 'ACTOR_STOPPED'
        assert worker._actor is None
        assert worker._actor_thread is None

    def test_stop_calls_disconnect(self, worker, mock_plugin_class):
        mock_actor = MagicMock()
        mock_actor.get_capabilities.return_value = {'observables': [], 'variables': []}

        with patch('pymodaq.utils.leco.actor_gui.PymodaqActor', return_value=mock_actor):
            worker.init_instrument(mock_plugin_class, 'myactor', 'localhost', 12300)
        worker.stop_actor()

        mock_actor.disconnect.assert_called_once()

    def test_stop_without_start_is_safe(self, worker):
        """stop_actor on a fresh worker must not raise."""
        received = []
        worker.status_sig.connect(received.append)
        worker.stop_actor()
        assert received[0].command == 'ACTOR_STOPPED'


# ── Qt-dependent GUI tests ─────────────────────────────────────────────────────

_QT_AVAILABLE = False
try:
    import pytest_qt  # noqa: F401
    from PyQt5 import QtWidgets as _qtw  # noqa: F401
    _QT_AVAILABLE = True
except ImportError:
    try:
        from PySide6 import QtWidgets as _qtw  # noqa: F401
        _QT_AVAILABLE = True
    except ImportError:
        pass

pytestmark_qt = pytest.mark.skipif(not _QT_AVAILABLE, reason='Qt / pytest-qt not available')


@pytest.fixture()
def caps_simple():
    from pymodaq.control_modules.capabilities import (
        Capabilities, ContinuousVariable, Observable,
    )
    return Capabilities(
        variables=[ContinuousVariable('position', units='mm', lo=-100.0, hi=100.0, epsilon=0.001)],
        observables=[Observable('frame', shape=(64, 64), dtype='float32')],
    )


@pytest.fixture()
def bare_gui(qtbot):
    pytest.importorskip('pytest_qt')
    from pymodaq.utils.leco.actor_gui import PymodaqActorGUI
    from pymodaq_gui.utils.dock import DockArea
    from qtpy.QtWidgets import QMainWindow

    win = QMainWindow()
    area = DockArea()
    win.setCentralWidget(area)

    with (
        patch('pymodaq.utils.leco.actor_gui.HARDWARE_REGISTRY', []),
        patch('pymodaq.utils.leco.actor_gui.HARDWARE_NAMES', []),
    ):
        g = PymodaqActorGUI(area)
        win.show()
        qtbot.addWidget(win)
        yield g

    g.worker_thread.quit()
    g.worker_thread.wait()


@pytestmark_qt
class TestGUIInstrumentList:
    def test_instrument_limits_populated(self, qtbot, mock_plugin_class):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.actor_gui import PymodaqActorGUI
        from pymodaq_gui.utils.dock import DockArea
        from qtpy.QtWidgets import QMainWindow

        win = QMainWindow()
        area = DockArea()
        win.setCentralWidget(area)
        registry = [_make_registry_entry('FakeStage', mock_plugin_class)]

        with (
            patch('pymodaq.utils.leco.actor_gui.HARDWARE_REGISTRY', registry),
            patch('pymodaq.utils.leco.actor_gui.HARDWARE_NAMES', ['FakeStage']),
        ):
            g = PymodaqActorGUI(area)
            qtbot.addWidget(win)
            limits = g.settings.child('instrument').opts.get('limits', [])
            assert 'FakeStage' in limits

        g.worker_thread.quit()
        g.worker_thread.wait()

    def test_empty_registry_shows_status_message(self, qtbot):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.actor_gui import PymodaqActorGUI
        from pymodaq_gui.utils.dock import DockArea
        from qtpy.QtWidgets import QMainWindow

        win = QMainWindow()
        area = DockArea()
        win.setCentralWidget(area)

        with (
            patch('pymodaq.utils.leco.actor_gui.HARDWARE_REGISTRY', []),
            patch('pymodaq.utils.leco.actor_gui.HARDWARE_NAMES', []),
        ):
            g = PymodaqActorGUI(area)
            qtbot.addWidget(win)
            msg = g.statusbar.currentMessage()
            assert 'No hardware' in msg or 'entry points' in msg

        g.worker_thread.quit()
        g.worker_thread.wait()


@pytestmark_qt
class TestCapsTree:
    def test_populate_does_not_raise(self, qtbot, caps_simple):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.actor_gui import PymodaqActorGUI
        from pymodaq_gui.utils.dock import DockArea
        from qtpy.QtWidgets import QMainWindow

        win = QMainWindow()
        area = DockArea()
        win.setCentralWidget(area)

        with (
            patch('pymodaq.utils.leco.actor_gui.HARDWARE_REGISTRY', []),
            patch('pymodaq.utils.leco.actor_gui.HARDWARE_NAMES', []),
        ):
            g = PymodaqActorGUI(area)
            qtbot.addWidget(win)
            g._populate_caps_tree(caps_simple)

        assert g._caps_tree is not None
        g.worker_thread.quit()
        g.worker_thread.wait()


@pytestmark_qt
class TestStatusHandling:
    def test_actor_ready_all_leds_green(self, bare_gui, caps_simple):
        bare_gui._on_status(ThreadCommand('ACTOR_READY', caps_simple))
        assert bare_gui.led_instrument.state is True
        assert bare_gui.led_coordinator.state is True
        assert bare_gui.led_actor.state is True
        assert bare_gui.get_action('stop').isEnabled()
        assert not bare_gui.get_action('init').isEnabled()

    def test_actor_stopped_all_leds_grey(self, bare_gui):
        bare_gui._on_status(ThreadCommand('ACTOR_STOPPED', None))
        assert bare_gui.led_instrument.state is False
        assert bare_gui.led_coordinator.state is False
        assert bare_gui.led_actor.state is False
        assert bare_gui.get_action('init').isEnabled()
        assert not bare_gui.get_action('stop').isEnabled()

    def test_error_all_leds_grey_init_re_enabled(self, bare_gui):
        bare_gui.led_instrument.set_as(True)
        bare_gui._on_status(ThreadCommand('ERROR', 'something broke'))
        assert bare_gui.led_instrument.state is False
        assert bare_gui.led_coordinator.state is False
        assert bare_gui.led_actor.state is False
        assert bare_gui.get_action('init').isEnabled()
        assert not bare_gui.get_action('stop').isEnabled()
        assert 'something broke' in bare_gui.statusbar.currentMessage()

    def test_actor_stopped_reverts_to_preview(self, qtbot, mock_plugin_class, caps_simple):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.actor_gui import PymodaqActorGUI
        from pymodaq_gui.utils.dock import DockArea
        from qtpy.QtWidgets import QMainWindow

        win = QMainWindow()
        area = DockArea()
        win.setCentralWidget(area)

        registry = [_make_registry_entry('MockStage', mock_plugin_class, caps_simple)]

        with (
            patch('pymodaq.utils.leco.actor_gui.HARDWARE_REGISTRY', registry),
            patch('pymodaq.utils.leco.actor_gui.HARDWARE_NAMES', ['MockStage']),
        ):
            g = PymodaqActorGUI(area)
            qtbot.addWidget(win)

            preview_calls = []
            original = g._on_instrument_selected
            g._on_instrument_selected = lambda: preview_calls.append(1) or original()

            g._on_status(ThreadCommand('ACTOR_STOPPED', None))
            assert len(preview_calls) == 1

        g.worker_thread.quit()
        g.worker_thread.wait()
