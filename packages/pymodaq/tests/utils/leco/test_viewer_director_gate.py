"""Tests for the _accepting_data gate flag in DAQ_xDViewer_LECODirector.

Tests the snap/live gate without requiring a Qt backend.
We stub the heavy base-class chain and exercise only the gate logic in
_on_actor_data / grab_data / stop / on_acquisition_status.

The new actor loop architecture (instruction-queue):
  - Live mode uses count=inf (no sequential round-trip mode).
  - on_acquisition_status(read_list, is_grabbing) replaces on_grab_status.
  - _live_sequential has been removed.
"""
from __future__ import annotations

import math
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

class _FakeController:
    def __init__(self):
        self.query_data_calls: list = []
        self.stop_calls: list = []

    def query_data(self, names=None, count=1, fresh=True, period=0.0):
        self.query_data_calls.append({
            'names': names, 'count': count, 'fresh': fresh, 'period': period,
        })

    def stop(self, names=None):
        self.stop_calls.append(names)


class _DirectorUnderTest:
    """
    Minimal shim that reproduces the gate-flag logic from
    DAQ_xDViewer_LECODirector without importing the full class.

    Matches the new instruction-queue architecture:
      - Live mode: query_data(count=inf)
      - No _live_sequential.
      - on_acquisition_status(read_list, is_grabbing) for remote state mirroring.
    """

    def __init__(self):
        self.controller = _FakeController()
        self.dte_signal = _Sig()
        self._accepting_data = False
        self._live_grab = False
        self._emitted: list = []
        self._statuses: list = []
        self.dte_signal.connect(self._emitted.append)
        self._settings = {
            'observable_name': 'spectrum',
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
            rate_hz = self._settings['max_rate_hz']
            period = 1.0 / rate_hz if rate_hz > 0 else 0.0
            self.controller.query_data(
                names=obs_names,
                count=math.inf,
                fresh=True,
                period=period,
            )
        else:
            self.controller.query_data(names=obs_names, count=1, fresh=True)

    def stop(self):
        self._accepting_data = False
        self._live_grab = False
        obs_name = self._settings['observable_name'] or None
        self.controller.stop(names=[obs_name] if obs_name else None)

    def _on_actor_data(self, topic: str, dte) -> None:
        if not self._accepting_data or dte is None:
            return
        self.dte_signal.emit(dte)
        if not self._live_grab:
            # Snap mode: one frame consumed — go idle until next grab_data() call.
            self._accepting_data = False

    def on_acquisition_status(self, read_list: dict, is_grabbing: bool) -> None:
        """Mirror the actor's acquisition state (new API)."""
        obs_name = self._settings['observable_name'] or 'data'
        if is_grabbing and (obs_name in read_list or '__all__' in read_list):
            self._accepting_data = True
            self._live_grab = True
        elif not is_grabbing:
            self._accepting_data = False
            self._live_grab = False
        self._statuses.append({'read_list': read_list, 'is_grabbing': is_grabbing})


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def director():
    return _DirectorUnderTest()


# ── Tests: initial state ──────────────────────────────────────────────────────

def test_initial_gate_closed(director):
    assert director._accepting_data is False


def test_no_live_sequential_attribute(director):
    """_live_sequential was removed in the instruction-queue refactor."""
    assert not hasattr(director, '_live_sequential')


def test_idle_frame_dropped(director):
    """Frames arriving before any grab_data() are silently dropped."""
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._emitted == []


# ── Tests: snap mode ─────────────────────────────────────────────────────────

def test_snap_opens_gate(director):
    director.grab_data(live=False)
    assert director._accepting_data is True


def test_snap_sends_count_1(director):
    director.grab_data(live=False)
    call = director.controller.query_data_calls[-1]
    assert call['count'] == 1


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


# ── Tests: live (continuous) mode ─────────────────────────────────────────────

def test_live_opens_gate(director):
    director.grab_data(live=True)
    assert director._accepting_data is True


def test_live_sends_count_inf(director):
    director.grab_data(live=True)
    call = director.controller.query_data_calls[-1]
    assert call['count'] == math.inf


def test_live_sends_period_from_rate(director):
    director._settings['max_rate_hz'] = 20.0
    director.grab_data(live=True)
    call = director.controller.query_data_calls[-1]
    assert abs(call['period'] - 0.05) < 1e-9


def test_live_gate_stays_open_after_frame(director):
    director.grab_data(live=True)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._accepting_data is True


def test_live_multiple_frames_all_emitted(director):
    director.grab_data(live=True)
    for _ in range(3):
        director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert len(director._emitted) == 3


def test_stop_closes_gate(director):
    director.grab_data(live=True)
    director.stop()
    assert director._accepting_data is False


def test_stop_sends_stop_to_controller(director):
    director.grab_data(live=True)
    director.stop()
    assert director.controller.stop_calls == [['spectrum']]


def test_stop_drops_subsequent_frames(director):
    director.grab_data(live=True)
    director.stop()
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._emitted == []


# ── Tests: on_acquisition_status (remote mirror) ──────────────────────────────

def test_on_acquisition_status_grabbing_obs_opens_gate(director):
    director.on_acquisition_status({'spectrum': {'period': 0.1}}, is_grabbing=True)
    assert director._accepting_data is True


def test_on_acquisition_status_grabbing_obs_accepts_frames(director):
    director.on_acquisition_status({'spectrum': {'period': 0.1}}, is_grabbing=True)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert len(director._emitted) == 1


def test_on_acquisition_status_all_opens_gate(director):
    """__all__ key means all observables are being grabbed."""
    director.on_acquisition_status({'__all__': {'period': 0.0}}, is_grabbing=True)
    assert director._accepting_data is True


def test_on_acquisition_status_other_obs_doesnt_open(director):
    """A different observable being grabbed must not open our gate."""
    director.on_acquisition_status({'other_channel': {}}, is_grabbing=True)
    assert director._accepting_data is False


def test_on_acquisition_status_stopped_closes_gate(director):
    director.on_acquisition_status({'spectrum': {}}, is_grabbing=True)
    director.on_acquisition_status({}, is_grabbing=False)
    assert director._accepting_data is False


def test_on_acquisition_status_stopped_drops_frames(director):
    director.on_acquisition_status({'spectrum': {}}, is_grabbing=True)
    director.on_acquisition_status({}, is_grabbing=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._emitted == []


def test_on_acquisition_status_records_status(director):
    director.on_acquisition_status({'spectrum': {}}, is_grabbing=True)
    assert director._statuses[-1] == {
        'read_list': {'spectrum': {}}, 'is_grabbing': True,
    }


# ── Tests: re-grab after snap ─────────────────────────────────────────────────

def test_second_snap_works_after_first(director):
    """grab_data() re-opens the gate even if it was closed by a previous snap."""
    director.grab_data(live=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert director._accepting_data is False
    director.grab_data(live=False)
    director._on_actor_data('topic/spectrum', _FakeDTE('spectrum'))
    assert len(director._emitted) == 2
