"""Tests for the _accepting_data gate flag in DAQ_xDViewer_LECODirector.

Tests the B5 snap/idle gate without requiring a Qt backend.
We stub the heavy base-class chain (DAQ_Viewer_base, LECODirector) and
exercise only the gate logic in _on_actor_data / grab_data / stop /
on_grab_status.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest


# ── Minimal stubs so the module imports without Qt ────────────────────────────

def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Only stub what's not already present (conftest may have set some up)
for _pkg in (
    'pymodaq', 'pymodaq.control_modules', 'pymodaq.utils', 'pymodaq.utils.leco',
    'pymodaq_gui', 'pymodaq_gui.parameter',
    'pymodaq.utils.data', 'pymodaq.utils.leco.utils',
    'pymodaq.control_modules.thread_commands',
    'serializall',
):
    if _pkg not in sys.modules:
        sys.modules[_pkg] = MagicMock()

if 'pymodaq_utils.utils' not in sys.modules:
    class _TC:
        def __init__(self, command, attribute=None, **kw):
            self.command = command
            self.attribute = attribute
    _stub('pymodaq_utils.utils', ThreadCommand=_TC)

if 'pymodaq_utils.logger' not in sys.modules:
    _stub('pymodaq_utils.logger',
          set_logger=lambda *a, **k: MagicMock(),
          get_module_name=lambda *a: 'test')

if 'pymodaq_data' not in sys.modules:
    sys.modules['pymodaq_data'] = MagicMock()

# ThreadCommand accessible from conftest path too
_ThreadCommand = sys.modules['pymodaq_utils.utils'].ThreadCommand


# ── Fake Signal ───────────────────────────────────────────────────────────────

class _Sig:
    def __init__(self): self._slots = []
    def connect(self, s): self._slots.append(s)
    def emit(self, *a):
        for s in self._slots:
            s(*a)


# ── Minimal fake DTE ─────────────────────────────────────────────────────────

class _FakeDWA:
    def __init__(self, name):
        self.name = name
        self.data = [np.zeros(1)]


class _FakeDTE:
    def __init__(self, *dwa_names):
        self.name = 'fake'
        self.data = [_FakeDWA(n) for n in dwa_names]


# ── Director stub ─────────────────────────────────────────────────────────────

class _FakeListener:
    """Minimal listener stub with a data_signal."""
    def __init__(self):
        self.signals = MagicMock()
        self.signals.data_signal = _Sig()
    def subscribe(self, topic): pass
    def unsubscribe(self, topic): pass


class _FakeController:
    def __init__(self):
        self.query_data_calls = []
        self.stop_continuous_called = False
    def query_data(self, names=None, fresh=True):
        self.query_data_calls.append(names)
    def stop_continuous(self):
        self.stop_continuous_called = True


class _DirectorUnderTest:
    """
    Minimal shim that reproduces only the gate-flag logic from
    DAQ_xDViewer_LECODirector without importing the full class.
    """

    def __init__(self):
        self.controller = _FakeController()
        self.listener = _FakeListener()
        self.dte_signal = _Sig()
        self._live_sequential = False
        self._accepting_data = False
        self._live_grab = False
        self._emitted: list = []
        self._statuses: list = []
        self.dte_signal.connect(self._emitted.append)
        # mirror settings dict
        self._settings = {
            'use_legacy_actor': False,
            'observable_name': 'spectrum',
            'live_mode': 'sequential',
            'max_rate_hz': 10.0,
        }

    def settings(self, key):
        return self._settings[key]

    # ── copied gate logic ──────────────────────────────────────────────────────

    def grab_data(self, Naverage=1, **kwargs):
        live = kwargs.get('live', False)
        self._accepting_data = True
        self._live_grab = bool(live)
        obs_name = self._settings['observable_name'] or None
        obs_names = [obs_name] if obs_name else None
        if live:
            if self._settings['live_mode'] == 'sequential':
                self._live_sequential = True
                self.controller.query_data(names=obs_names, fresh=True)
            else:
                self._live_sequential = False
                self.controller.query_data_calls.append('continuous_start')
        else:
            self._live_sequential = False
            self.controller.query_data(names=obs_names, fresh=True)

    def stop(self):
        self._accepting_data = False
        self._live_sequential = False
        self._live_grab = False
        if self._settings['live_mode'] == 'continuous':
            self.controller.stop_continuous()

    def _on_actor_data(self, topic: str, dte) -> None:
        if not self._accepting_data or dte is None:
            return
        self.dte_signal.emit(dte)
        if self._live_sequential:
            obs_name = self._settings['observable_name'] or None
            try:
                self.controller.query_data(
                    names=[obs_name] if obs_name else None, fresh=True
                )
            except Exception:
                self._live_sequential = False
        elif not self._live_grab:
            # snap mode: one frame consumed
            self._accepting_data = False

    def on_grab_status(self, grabbed_names, is_continuous: bool) -> None:
        if is_continuous:
            self._accepting_data = True
            self._live_grab = True
        else:
            self._accepting_data = False
            self._live_sequential = False
            self._live_grab = False
        self._statuses.append({'grabbed_names': grabbed_names, 'is_continuous': is_continuous})

    def emit_status(self, cmd): pass


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def director():
    return _DirectorUnderTest()


# ── Tests: initial state ──────────────────────────────────────────────────────

def test_initial_gate_closed(director):
    assert director._accepting_data is False


def test_idle_frame_dropped(director):
    """Frames arriving before any grab_data() are silently dropped."""
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._emitted == []


# ── Tests: snap mode ─────────────────────────────────────────────────────────

def test_snap_opens_gate(director):
    director.grab_data(live=False)
    assert director._accepting_data is True


def test_snap_first_frame_emitted(director):
    director.grab_data(live=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert len(director._emitted) == 1


def test_snap_gate_closed_after_first_frame(director):
    """After one snap frame the gate closes — no further frames processed."""
    director.grab_data(live=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._accepting_data is False


def test_snap_second_frame_dropped(director):
    """Spurious second frame (e.g. from actor periodic timer) is not emitted."""
    director.grab_data(live=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert len(director._emitted) == 1


def test_snap_none_dte_ignored(director):
    director.grab_data(live=False)
    director._on_actor_data('topic/spectrum', None)
    assert director._emitted == []


# ── Tests: sequential live mode ──────────────────────────────────────────────

def test_sequential_live_opens_gate(director):
    director.grab_data(live=True)
    assert director._accepting_data is True


def test_sequential_live_gate_stays_open_after_frame(director):
    """In sequential mode the gate stays open — each frame triggers the next request."""
    director.grab_data(live=True)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._accepting_data is True


def test_sequential_live_multiple_frames_all_emitted(director):
    director.grab_data(live=True)
    for _ in range(3):
        director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert len(director._emitted) == 3


def test_stop_closes_gate(director):
    director.grab_data(live=True)
    director.stop()
    assert director._accepting_data is False


def test_stop_drops_subsequent_frames(director):
    director.grab_data(live=True)
    director.stop()
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._emitted == []


# ── Tests: continuous live mode ───────────────────────────────────────────────

def test_continuous_live_gate_stays_open(director):
    director._settings['live_mode'] = 'continuous'
    director.grab_data(live=True)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._accepting_data is True
    assert len(director._emitted) == 2


# ── Tests: mirror mode (on_grab_status) ──────────────────────────────────────

def test_on_grab_status_continuous_opens_gate(director):
    director.on_grab_status(['spectrum'], is_continuous=True)
    assert director._accepting_data is True


def test_on_grab_status_continuous_accepts_frames(director):
    director.on_grab_status(['spectrum'], is_continuous=True)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert len(director._emitted) == 1


def test_on_grab_status_stopped_closes_gate(director):
    director.on_grab_status(['spectrum'], is_continuous=True)
    director.on_grab_status(None, is_continuous=False)
    assert director._accepting_data is False


def test_on_grab_status_stopped_drops_frames(director):
    director.on_grab_status(['spectrum'], is_continuous=True)
    director.on_grab_status(None, is_continuous=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._emitted == []


def test_on_grab_status_records_status(director):
    director.on_grab_status(['spectrum'], is_continuous=True)
    assert director._statuses[-1] == {'grabbed_names': ['spectrum'], 'is_continuous': True}


# ── Tests: re-grab after snap ─────────────────────────────────────────────────

def test_second_snap_works_after_first(director):
    """grab_data() re-opens the gate even if it was closed by a previous snap."""
    director.grab_data(live=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._accepting_data is False
    director.grab_data(live=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert len(director._emitted) == 2
