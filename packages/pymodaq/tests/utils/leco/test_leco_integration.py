"""Integration tests: PymodaqActor ↔ PymodaqMoveDirector / PymodaqDetectorDirector.

Pure Python — no Qt, no real LECO network.

Pattern: create actor with FakeContext; call handle_request_message(actor, method, **kwargs)
to simulate an RPC arriving at the actor; verify actor state and/or published frames.
"""
import json
import numpy as np
import pytest
from serializall import SerializableFactory

from pyleco.test import FakeContext, FakeDirector, FakeCommunicator, handle_request_message

from pymodaq.utils.leco.actor import PymodaqActor
from pymodaq.control_modules.capabilities import Capabilities, Observable, ContinuousVariable
from pymodaq.utils.leco.director_utils import PymodaqMoveDirector, PymodaqDetectorDirector


# ── Mock devices ───────────────────────────────────────────────────────────────

class MockCamera:
    capabilities = Capabilities(
        observables=[Observable('frame', shape=(4, 4), dtype='float64')],
    )

    def __init__(self):
        self.read_count = 0

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        self.read_count += 1
        return DataToExport('cam', data=[DataRaw('frame', data=[np.zeros((4, 4))])])


class MockStage:
    _controller_units = 'mm'
    _axis_names = None
    _epsilons = 0.001

    def __init__(self):
        self._position = 0.0
        self.read_count = 0
        self.write_calls = []

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        self.read_count += 1
        return DataToExport('stage', data=[DataRaw('position', data=[np.array([self._position])])])

    def write(self, name, value):
        if name == 'position':
            self._position = float(value)
        self.write_calls.append((name, value))


# ── Fake directors ─────────────────────────────────────────────────────────────

class FakeMoveDirector(FakeDirector, PymodaqMoveDirector):
    pass


class FakeDetectorDirector(FakeDirector, PymodaqDetectorDirector):
    pass


# ── Helpers ────────────────────────────────────────────────────────────────────

def _last_rpc_result(actor: PymodaqActor) -> object:
    """Extract the JSON-RPC result value from the last message sent by the actor."""
    frames = actor.socket._s[-1]
    for frame in frames:
        try:
            parsed = json.loads(frame.decode())
            if isinstance(parsed, dict) and 'result' in parsed:
                return parsed['result']
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
    raise AssertionError("No RPC result found in actor's sent frames")


def _published(actor: PymodaqActor) -> list:
    """Return all frames published by the actor's DataPublisher."""
    return actor.publisher.socket._s


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def stage_actor():
    actor = PymodaqActor('N.stage', MockStage, context=FakeContext())
    actor.connect()
    return actor


@pytest.fixture
def camera_actor():
    actor = PymodaqActor('N.cam', MockCamera, context=FakeContext())
    actor.connect()
    return actor


@pytest.fixture
def move_director(stage_actor):
    d = FakeMoveDirector(remote_class=stage_actor.__class__)
    d.communicator = FakeCommunicator('N.dashboard')
    d.return_value = None
    return d


@pytest.fixture
def detector_director(camera_actor):
    d = FakeDetectorDirector(remote_class=camera_actor.__class__)
    d.communicator = FakeCommunicator('N.dashboard')
    d.return_value = None
    return d


# ── Actor-side tests (RPC → device state / ZMQ publish) ───────────────────────

class TestMoveActorRPC:

    def test_change_to_writes_device(self, stage_actor):
        handle_request_message(stage_actor, 'change_to', name='position', value=12.5)
        assert stage_actor.device._position == pytest.approx(12.5)

    def test_change_to_auto_publishes(self, stage_actor):
        """change_to must publish updated state immediately (no extra query_data needed)."""
        handle_request_message(stage_actor, 'change_to', name='position', value=5.0)
        assert len(_published(stage_actor)) >= 1
        assert stage_actor.device.read_count >= 1

    def test_query_data_publishes(self, stage_actor):
        handle_request_message(stage_actor, 'query_data', names=None, fresh=True)
        assert len(_published(stage_actor)) == 1
        assert stage_actor.device.read_count == 1

    def test_query_data_fresh_false_no_new_read(self, stage_actor):
        handle_request_message(stage_actor, 'query_data', names=None, fresh=True)
        count_before = stage_actor.device.read_count
        handle_request_message(stage_actor, 'query_data', names=None, fresh=False)
        assert stage_actor.device.read_count == count_before
        assert len(_published(stage_actor)) == 2

    def test_get_capabilities_returns_dict(self, stage_actor):
        handle_request_message(stage_actor, 'get_capabilities')
        result = _last_rpc_result(stage_actor)
        assert isinstance(result, dict)

    def test_capabilities_has_position_variable(self, stage_actor):
        handle_request_message(stage_actor, 'get_capabilities')
        caps = Capabilities.from_dict(_last_rpc_result(stage_actor))
        assert len(caps.variables) == 1
        assert caps.variables[0].name == 'position'

    def test_subscribe_director(self, stage_actor):
        handle_request_message(stage_actor, 'subscribe_director', name='N.dashboard')
        assert 'N.dashboard' in stage_actor._director_registry

    def test_unsubscribe_director(self, stage_actor):
        handle_request_message(stage_actor, 'subscribe_director', name='N.dashboard')
        handle_request_message(stage_actor, 'unsubscribe_director', name='N.dashboard')
        assert 'N.dashboard' not in stage_actor._director_registry

    def test_change_to_list(self, stage_actor):
        handle_request_message(stage_actor, 'change_to', name=['position'], value=[7.0])
        assert stage_actor.device._position == pytest.approx(7.0)

    def test_query_data_returns_cid(self, stage_actor):
        """query_data RPC must return a hex CID string, not None."""
        handle_request_message(stage_actor, 'query_data', names=None, fresh=True)
        cid = _last_rpc_result(stage_actor)
        assert isinstance(cid, str)
        assert len(cid) == 32  # 16 bytes hex-encoded

    def test_change_to_returns_cid(self, stage_actor):
        """change_to RPC must return the CID of its auto-publish."""
        handle_request_message(stage_actor, 'change_to', name='position', value=3.0)
        cid = _last_rpc_result(stage_actor)
        assert isinstance(cid, str)
        assert len(cid) == 32

    def test_cid_matches_zmq_frame(self, stage_actor):
        """CID returned by query_data must match the header of the published ZMQ frame."""
        handle_request_message(stage_actor, 'query_data', names=None, fresh=True)
        cid_rpc = _last_rpc_result(stage_actor)
        # DataMessage frame layout: [topic, header(17B), payload]
        # header = CID(16B) + message_type(1B)
        zmq_frame_header = _published(stage_actor)[-1][1]
        cid_zmq = zmq_frame_header[:16].hex()
        assert cid_rpc == cid_zmq

    def test_change_to_cid_matches_zmq_frame(self, stage_actor):
        """CID returned by change_to must match the header of the auto-published frame."""
        handle_request_message(stage_actor, 'change_to', name='position', value=8.0)
        cid_rpc = _last_rpc_result(stage_actor)
        zmq_frame_header = _published(stage_actor)[-1][1]
        cid_zmq = zmq_frame_header[:16].hex()
        assert cid_rpc == cid_zmq


class TestDetectorActorRPC:

    def test_query_data_reads_device(self, camera_actor):
        handle_request_message(camera_actor, 'query_data', names=None, fresh=True)
        assert camera_actor.device.read_count == 1

    def test_query_data_published_deserializes(self, camera_actor):
        from pymodaq_data.data import DataToExport
        handle_request_message(camera_actor, 'query_data', names=None, fresh=True)
        payload = _published(camera_actor)[0][2]
        dte = SerializableFactory().get_apply_deserializer(payload)
        assert isinstance(dte, DataToExport)
        assert dte.name == 'cam'

    def test_capabilities_has_observable(self, camera_actor):
        handle_request_message(camera_actor, 'get_capabilities')
        caps = Capabilities.from_dict(_last_rpc_result(camera_actor))
        assert len(caps.observables) == 1
        assert caps.observables[0].name == 'frame'


class TestDirectorSideRPC:
    """FakeDirector verifies that director methods send the correct actor RPC names."""

    def test_move_change_to(self, move_director):
        move_director.change_to('position', 5.0)
        assert move_director.method == 'change_to'
        assert move_director.kwargs == {'name': 'position', 'value': 5.0}

    def test_move_query_data(self, move_director):
        move_director.query_data(fresh=True)
        assert move_director.method == 'query_data'
        assert move_director.kwargs['fresh'] is True

    def test_detector_query_data(self, detector_director):
        detector_director.query_data(names='frame', fresh=True)
        assert detector_director.method == 'query_data'
        assert detector_director.kwargs['names'] == 'frame'

    def test_get_capabilities_round_trip(self, stage_actor):
        """Actor-side: get_capabilities RPC → deserializes to Capabilities with position variable."""
        handle_request_message(stage_actor, 'get_capabilities')
        caps = Capabilities.from_dict(_last_rpc_result(stage_actor))
        assert isinstance(caps, Capabilities)
        assert caps.variables[0].name == 'position'
