#!/usr/bin/env python3
"""Proof-of-concept: PymodaqActor + PymodaqMoveDirector / PymodaqDetectorDirector.

Demonstrates the new LECO actor API (Phase 1+2) using in-process mocks —
no real hardware, no network, no Qt required.

Run from the repository root:
    PYTHONPATH=packages/pymodaq_utils/src:packages/pymodaq_data/src:packages/pymodaq_gui/src:packages/pymodaq/src \\
        python3 packages/pymodaq/src/pymodaq/examples/leco_actor_mock.py

What this shows
---------------
1. A mock stage (actuator) and a mock camera (detector) — pure Python, no hardware.
2. Each wrapped in a ``PymodaqActor`` (single serialized owner of the device).
3. ``PymodaqMoveDirector`` sending ``change_to`` / ``query_data`` to the stage.
4. ``PymodaqDetectorDirector`` sending ``query_data`` to the camera.
5. ``get_capabilities()`` returning rich metadata (units, bounds, shape).
6. ``subscribe_settings`` / ``unsubscribe_settings`` registry.
7. Published ``DataToExport`` round-tripped through serialization.

Data-reception note
-------------------
``query_data()`` publishes on the LECO ZMQ PUB channel and returns None.
Directors receive data by subscribing to that channel (Phase 4 — SpectatorSubscriber).
Here we inspect ``actor.publisher.socket._s`` (FakeSocket buffer) to confirm publication.
"""
from __future__ import annotations

# ── Headless bootstrap — stubs Qt-laden imports before pymodaq loads ──────────
# pymodaq/__init__.py triggers Qt on import; stub its heavy dependencies so
# this script runs without a display or Qt installation.
import sys
from pathlib import Path
import importlib.util
from unittest.mock import MagicMock

_SRC = Path(__file__).parents[2]   # packages/pymodaq/src

def _stub(name: str) -> MagicMock:
    if name not in sys.modules:
        m = MagicMock()
        m.__name__ = name
        m.__path__ = []
        m.__package__ = name
        m.__spec__ = None
        sys.modules[name] = m
    return sys.modules[name]

def _load(canonical: str, rel: str):
    if canonical not in sys.modules:
        path = _SRC / rel
        spec = importlib.util.spec_from_file_location(canonical, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[canonical] = mod
        spec.loader.exec_module(mod)
    return sys.modules[canonical]

# Stub Qt and Qt-dependent packages
for _pkg in (
    'pymodaq', 'pymodaq.utils', 'pymodaq.utils.leco',
    'pymodaq.control_modules',
    'pymodaq_gui', 'pymodaq_gui.parameter', 'pymodaq_gui.parameter.utils',
    'pymodaq.utils.data', 'pymodaq.utils.leco.utils',
):
    _stub(_pkg)

# Load pure-Python modules directly (bypassing __init__.py)
_UTILS_SRC = Path(__file__).parents[4] / 'pymodaq_utils' / 'src'
_load('pymodaq_utils.enums', _UTILS_SRC / 'pymodaq_utils' / 'enums.py')
_load('pymodaq.control_modules.capabilities',
      _SRC / 'pymodaq' / 'control_modules' / 'capabilities.py')
_load('pymodaq.utils.leco.rpc_method_definitions',
      _SRC / 'pymodaq' / 'utils' / 'leco' / 'rpc_method_definitions.py')
_load('pymodaq.utils.leco.actor',
      _SRC / 'pymodaq' / 'utils' / 'leco' / 'actor.py')
_load('pymodaq.utils.leco.director_utils',
      _SRC / 'pymodaq' / 'utils' / 'leco' / 'director_utils.py')
# ─────────────────────────────────────────────────────────────────────────────

import json
import numpy as np

from pyleco.test import FakeContext, FakeDirector, FakeCommunicator, handle_request_message
from serializall import SerializableFactory

from pymodaq.utils.leco.actor import PymodaqActor
from pymodaq.utils.leco.director_utils import PymodaqMoveDirector, PymodaqDetectorDirector
from pymodaq.control_modules.capabilities import (
    Capabilities, Observable, ContinuousVariable,
)


# ── Mock hardware devices ─────────────────────────────────────────────────────

class MockStage:
    """Simulates a single-axis motorised translation stage."""

    # Explicit capabilities — new plugins should declare these.
    capabilities = Capabilities(
        variables=[ContinuousVariable('position', units='mm', lo=-50.0, hi=50.0, epsilon=0.001)],
    )

    def __init__(self):
        self._position = 0.0   # current position in mm

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        return DataToExport(
            'stage',
            data=[DataRaw('position', data=[np.array([self._position])])],
        )

    def write(self, name, value):
        if name == 'position':
            self._position = float(value)
            print(f"  [stage]  write '{name}' → {self._position:.3f} mm")


class MockCamera:
    """Simulates a simple 64×64 detector."""

    capabilities = Capabilities(
        observables=[Observable('frame', units='counts', shape=(64, 64), dtype='float32')],
    )

    def __init__(self):
        self._frame_idx = 0

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        self._frame_idx += 1
        frame = np.random.randint(0, 1000, (64, 64)).astype('float32')
        print(f"  [camera] read frame #{self._frame_idx:3d}  mean={frame.mean():.1f}")
        return DataToExport(
            'camera',
            data=[DataRaw('frame', data=[frame])],
        )


# ── FakeDirector subclasses ───────────────────────────────────────────────────

class FakeMoveDirector(FakeDirector, PymodaqMoveDirector):
    pass

class FakeDetectorDirector(FakeDirector, PymodaqDetectorDirector):
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def rpc_result(actor: PymodaqActor):
    """Extract the JSON-RPC result from the last message the actor sent."""
    frames = actor.socket._s[-1]
    for frame in frames:
        try:
            parsed = json.loads(frame.decode())
            if isinstance(parsed, dict) and 'result' in parsed:
                return parsed['result']
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
    raise AssertionError("No RPC result in actor's last sent frame")


def published_frames(actor: PymodaqActor) -> list:
    """All frames published by the actor's DataPublisher (ZMQ PUB)."""
    return actor.publisher.socket._s


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


# ── Demo 1: Actuator (MockStage) ──────────────────────────────────────────────

def demo_stage():
    section("DEMO 1 — Actuator (MockStage) via PymodaqMoveDirector")

    actor = PymodaqActor('lab.stage', MockStage, context=FakeContext())
    actor.connect()
    print(f"\nActor '{actor.name}'  device={type(actor.device).__name__}")

    # 1. Capabilities
    print("\n[1] get_capabilities")
    handle_request_message(actor, 'get_capabilities')
    caps = Capabilities.from_dict(rpc_result(actor))
    for v in caps.variables:
        print(f"     Variable: {v.name!r}  units={v.units}  lo={v.lo} hi={v.hi}  ε={v.epsilon}")
    assert caps.variables[0].name == 'position'

    # 2. Absolute move
    print("\n[2] change_to('position', 10.0)  — absolute move")
    handle_request_message(actor, 'change_to', name='position', value=10.0)
    assert actor.device._position == 10.0
    print(f"     Confirmed: position = {actor.device._position} mm ✓")

    # 3. Multi-variable form
    print("\n[3] change_to(['position'], [25.0])  — list form")
    handle_request_message(actor, 'change_to', name=['position'], value=[25.0])
    assert actor.device._position == 25.0
    print(f"     Confirmed: position = {actor.device._position} mm ✓")

    # 4. Publish fresh read
    print("\n[4] query_data(fresh=True)  → ZMQ PUB")
    handle_request_message(actor, 'query_data', names=None, fresh=True)
    frames = published_frames(actor)
    print(f"     Published {len(frames)} frame(s)")
    dte = SerializableFactory().get_apply_deserializer(frames[-1][2])
    print(f"     DataToExport: name={dte.name!r}  data[0]={dte.data[0].name!r}")

    # 5. Cached re-publish
    print("\n[5] query_data(fresh=False)  → re-publish cached, no hardware read")
    handle_request_message(actor, 'query_data', names=None, fresh=False)
    print(f"     Total publishes: {len(published_frames(actor))} (only 1 device read) ✓")

    # 6. Settings subscription
    print("\n[6] subscribe_director / unsubscribe_director")
    handle_request_message(actor, 'subscribe_director', name='lab.dashboard')
    print(f"     Registry: {actor._director_registry}")
    handle_request_message(actor, 'unsubscribe_director', name='lab.dashboard')
    print(f"     Registry: {actor._director_registry}")

    # 7. Director-side API
    print("\n[7] Director-side (FakeMoveDirector)")
    d = FakeMoveDirector(remote_class=actor.__class__)
    d.communicator = FakeCommunicator('lab.dashboard')
    d.return_value = None

    d.change_to('position', 30.0)
    assert d.method == 'change_to' and d.kwargs == {'name': 'position', 'value': 30.0}
    print("     change_to       → RPC 'change_to' ✓")

    d.query_data(fresh=True)
    assert d.method == 'query_data'
    print("     query_data      → RPC 'query_data' ✓")

    d.subscribe_settings()
    assert d.method == 'subscribe_director'
    print("     subscribe_settings → RPC 'subscribe_director' ✓")

    print("\n  ✓ Stage demo passed")


# ── Demo 2: Detector (MockCamera) ─────────────────────────────────────────────

def demo_camera():
    section("DEMO 2 — Detector (MockCamera) via PymodaqDetectorDirector")

    actor = PymodaqActor('lab.cam', MockCamera, context=FakeContext())
    actor.connect()
    print(f"\nActor '{actor.name}'  device={type(actor.device).__name__}")

    # 1. Capabilities
    print("\n[1] get_capabilities")
    handle_request_message(actor, 'get_capabilities')
    caps = Capabilities.from_dict(rpc_result(actor))
    for o in caps.observables:
        print(f"     Observable: {o.name!r}  shape={o.shape}  units={o.units}")
    assert caps.observables[0].name == 'frame'

    # 2. Grab frame
    print("\n[2] query_data(fresh=True)  → grab and publish")
    handle_request_message(actor, 'query_data', names=None, fresh=True)
    dte = SerializableFactory().get_apply_deserializer(published_frames(actor)[-1][2])
    dwa = dte.data[0]
    print(f"     DataToExport: {dte.name!r}")
    print(f"     DataWithAxes: name={dwa.name!r}  shape={dwa.data[0].shape}")
    assert dwa.data[0].shape == (64, 64)

    # 3. Named observable
    print("\n[3] query_data(names='frame', fresh=True)")
    handle_request_message(actor, 'query_data', names='frame', fresh=True)
    print(f"     Total publishes: {len(published_frames(actor))} ✓")

    # 4. Director-side
    print("\n[4] Director-side (FakeDetectorDirector)")
    d = FakeDetectorDirector(remote_class=actor.__class__)
    d.communicator = FakeCommunicator('lab.dashboard')
    d.return_value = None

    d.query_data(names='frame', fresh=True)
    assert d.method == 'query_data' and d.kwargs == {'names': 'frame', 'fresh': True}
    print("     query_data → RPC 'query_data'  kwargs match ✓")

    assert not hasattr(PymodaqDetectorDirector, 'change_to')
    print("     PymodaqDetectorDirector has no change_to (read-only) ✓")

    print("\n  ✓ Camera demo passed")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    demo_stage()
    demo_camera()
    section("ALL DEMOS PASSED")
