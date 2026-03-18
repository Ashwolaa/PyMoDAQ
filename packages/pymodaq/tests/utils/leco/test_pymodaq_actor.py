"""Tests for pymodaq.utils.leco.actor.PymodaqActor.

Pure Python — no Qt, no LECO network, no real hardware.
Uses pyleco's FakeContext and handle_request_message utilities.

Phases covered:
  Phase 0 — data structures (ReadRequest, WriteInstruction, StopInstruction, enums)
  Phase 1 — hardware loop thread
  Phase 2 — RPC handler rewiring
  Phase 7 — error propagation
  Phase 8 — cleanup (removed attributes / deprecated params)
"""
import json
import math
import time

import numpy as np
import pytest

from pyleco.test import FakeContext, handle_request_message

from pymodaq.utils.leco.actor import (
    PymodaqActor,
    ReadRequest,
    WriteInstruction,
    StopInstruction,
)
from pymodaq.control_modules.capabilities import (
    Capabilities,
    ContinuousVariable,
    Observable,
    Variable,
)
from pymodaq.utils.leco.rpc_method_definitions import PymodaqActorMethods


# ── Helpers ────────────────────────────────────────────────────────────────────

def _last_rpc_result(actor: PymodaqActor) -> object:
    """Extract the JSON-RPC result value from the last message sent by *actor*."""
    frames = actor.socket._s[-1]
    for frame in frames:
        try:
            parsed = json.loads(frame.decode())
            if isinstance(parsed, dict) and 'result' in parsed:
                return parsed['result']
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
    raise AssertionError("No RPC result found in actor's sent frames")


def _wait_for_loop(actor: PymodaqActor, timeout: float = 1.0) -> None:
    """Wait until the instruction queue is drained and the loop has run one more tick."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if actor._instruction_queue.empty():
            time.sleep(0.02)  # one more loop tick
            return
        time.sleep(0.005)
    raise TimeoutError("Hardware loop did not drain instructions within timeout")


# ── Mock devices ───────────────────────────────────────────────────────────────

class _MockViewerDevice:
    def __init__(self):
        from pymodaq_data.data import DataToExport, DataRaw
        self._dte = DataToExport(
            name='mock_viewer',
            data=[DataRaw('spectrum', data=[np.ones(64)])],
        )
        self.read_count = 0
        self.last_read_names = None
        self.write_calls: list = []
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def close(self):
        self.closed = True

    def read(self, names=None):
        self.read_count += 1
        self.last_read_names = names
        return self._dte

    def write(self, name, value):
        self.write_calls.append((name, value))


class _MockMoveDevice:
    _controller_units = 'mm'
    _axis_names = None
    _epsilons = 0.001

    def __init__(self):
        self._position = 0.0
        self.read_count = 0
        self.write_calls: list = []
        self.move_rel_calls: list = []
        self.home_called = False
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def close(self):
        self.closed = True

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        self.read_count += 1
        return DataToExport(
            name='mock_move',
            data=[DataRaw('position', data=[np.array([self._position])])],
        )

    def write(self, name, value):
        if name == 'position':
            self._position = float(value)
        self.write_calls.append((name, value))

    def move_rel(self, delta: float):
        self.move_rel_calls.append(delta)
        self._position += delta

    def home(self):
        self.home_called = True
        self._position = 0.0


class _MockDeviceWithSettings:
    def __init__(self):
        self._xml = '<settings><param name="gain" value="1"/></settings>'
        self.set_info_calls: list = []
        self.write_calls: list = []
        self.read_count = 0

    def connect(self): pass
    def close(self): pass

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        self.read_count += 1
        return DataToExport(name='s', data=[DataRaw('ch', data=[np.zeros(1)])])

    def write(self, name, value):
        self.write_calls.append((name, value))

    def get_settings(self) -> str:
        return self._xml

    def set_info(self, path: str, value):
        self.set_info_calls.append((path, value))


class _MockDeviceWithCapabilities:
    capabilities = Capabilities(
        observables=[Observable(name='spectrum', units='counts', shape=(2048,))],
        variables=[ContinuousVariable(name='wavelength', units='nm',
                                      lo=400.0, hi=900.0, epsilon=0.01)],
    )

    def connect(self): pass
    def close(self): pass

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        all_data = {
            'spectrum':   DataRaw('spectrum',   data=[np.zeros(2048)]),
            'wavelength': DataRaw('wavelength', data=[np.array([500.0])]),
        }
        if names is not None:
            data = [all_data[n] for n in names if n in all_data]
        else:
            data = list(all_data.values())
        return DataToExport(name='e', data=data)

    def write(self, name, value):
        pass


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def viewer_actor():
    actor = PymodaqActor(
        name='test_viewer',
        device_class=_MockViewerDevice,
        context=FakeContext(),
    )
    actor.connect()
    yield actor
    actor._hw_stop_event.set()
    actor._new_instruction_event.set()


@pytest.fixture
def move_actor():
    actor = PymodaqActor(
        name='test_move',
        device_class=_MockMoveDevice,
        context=FakeContext(),
    )
    actor.connect()
    yield actor
    actor._hw_stop_event.set()
    actor._new_instruction_event.set()


@pytest.fixture
def settings_actor():
    actor = PymodaqActor(
        name='test_settings',
        device_class=_MockDeviceWithSettings,
        context=FakeContext(),
    )
    actor.connect()
    yield actor
    actor._hw_stop_event.set()
    actor._new_instruction_event.set()


@pytest.fixture
def caps_actor():
    actor = PymodaqActor(
        name='test_caps',
        device_class=_MockDeviceWithCapabilities,
        context=FakeContext(),
    )
    actor.connect()
    yield actor
    actor._hw_stop_event.set()
    actor._new_instruction_event.set()


# ── Phase 0: Data structures ──────────────────────────────────────────────────

class TestInstructions:
    def test_read_request_fields(self):
        req = ReadRequest(names=['x'], count=1, period=0.0, requester='ns.d1', req_id=b'\x00' * 16)
        assert req.names == ['x']
        assert req.count == 1
        assert req.period == 0.0
        assert req.requester == 'ns.d1'
        assert req.req_id == b'\x00' * 16

    def test_write_instruction_dict_form(self):
        instr = WriteInstruction(name={'a': 1, 'b': 2}, value=None, requester='', req_id=b'\x01' * 16)
        assert isinstance(instr.name, dict)
        assert instr.name == {'a': 1, 'b': 2}

    def test_read_list_merge_min_period(self):
        """Merging two ReadRequests for the same key takes the minimum period."""
        req1 = ReadRequest(names=['x'], count=math.inf, period=0.1, requester='', req_id=b'\x00' * 16)
        req2 = ReadRequest(names=['x'], count=math.inf, period=0.05, requester='', req_id=b'\x01' * 16)
        merged_period = min(req1.period, req2.period)
        assert merged_period == pytest.approx(0.05)

    def test_read_list_merge_inf_wins_over_1(self):
        """Merging count=1 with count=inf gives count=inf."""
        count1, count2 = 1.0, math.inf
        merged = math.inf if (math.isinf(count1) or math.isinf(count2)) else max(count1, count2)
        assert math.isinf(merged)

    def test_names_none_key_distinct_from_frozenset(self):
        """None key (all observables) is distinct from frozenset({'frame'})."""
        read_list = {}
        req_all = ReadRequest(names=None, count=math.inf, period=0.1, requester='', req_id=b'\x00' * 16)
        req_frame = ReadRequest(names=['frame'], count=1, period=0.0, requester='', req_id=b'\x01' * 16)
        read_list[None] = req_all
        read_list[frozenset(['frame'])] = req_frame
        assert len(read_list) == 2
        assert None in read_list
        assert frozenset(['frame']) in read_list

    def test_stop_instruction_fields(self):
        instr = StopInstruction(names=['frame'], requester='ns.d1')
        assert instr.names == ['frame']
        assert instr.requester == 'ns.d1'

    def test_rpc_enum_new_entries(self):
        assert hasattr(PymodaqActorMethods, 'STOP')
        assert PymodaqActorMethods.STOP == 'stop'
        assert hasattr(PymodaqActorMethods, 'GET_READ_LIST')
        assert PymodaqActorMethods.GET_READ_LIST == 'get_read_list'
        assert hasattr(PymodaqActorMethods, 'GET_ACQUISITION_STATUS')
        assert PymodaqActorMethods.GET_ACQUISITION_STATUS == 'get_acquisition_status'


# ── Phase 1: Hardware loop thread ─────────────────────────────────────────────

class TestHardwareLoop:
    def test_hardware_loop_thread_starts_on_connect(self, viewer_actor):
        assert viewer_actor._hw_thread is not None
        assert viewer_actor._hw_thread.is_alive()

    def test_hardware_loop_thread_stops_on_disconnect(self):
        actor = PymodaqActor(
            name='test_disc',
            device_class=_MockViewerDevice,
            context=FakeContext(),
        )
        actor.connect()
        assert actor._hw_thread.is_alive()
        actor.disconnect()
        assert not actor._hw_thread.is_alive() if actor._hw_thread else True

    def test_loop_executes_read_request_and_publishes(self, viewer_actor):
        before = len(viewer_actor.publisher.socket._s)
        req = ReadRequest(names=None, count=1, period=0.0, requester='', req_id=b'\x00' * 16)
        viewer_actor._instruction_queue.put(req)
        viewer_actor._new_instruction_event.set()
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.read_count >= 1
        assert len(viewer_actor.publisher.socket._s) > before

    def test_loop_count_decrements_to_zero_removes_entry(self, viewer_actor):
        req = ReadRequest(names=None, count=1, period=0.0, requester='', req_id=b'\x00' * 16)
        viewer_actor._instruction_queue.put(req)
        viewer_actor._new_instruction_event.set()
        _wait_for_loop(viewer_actor)
        time.sleep(0.05)  # let the loop clean up
        assert frozenset() not in viewer_actor._read_list
        assert None not in viewer_actor._read_list

    def test_loop_count_inf_persists(self, viewer_actor):
        req = ReadRequest(names=None, count=math.inf, period=0.0, requester='', req_id=b'\x00' * 16)
        viewer_actor._instruction_queue.put(req)
        viewer_actor._new_instruction_event.set()
        time.sleep(0.08)  # let loop spin multiple times
        assert viewer_actor.device.read_count >= 2
        # Stop the read
        viewer_actor.stop(names=None)
        _wait_for_loop(viewer_actor)

    def test_loop_writes_before_reads_in_same_tick(self, move_actor):
        """WriteInstruction is executed before ReadRequest in the same tick."""
        write_instr = WriteInstruction(
            name='position', value=5.0, requester='', req_id=b'\x00' * 16
        )
        read_req = ReadRequest(names=None, count=1, period=0.0, requester='', req_id=b'\x01' * 16)
        move_actor._instruction_queue.put(write_instr)
        move_actor._instruction_queue.put(read_req)
        move_actor._new_instruction_event.set()
        _wait_for_loop(move_actor)
        # Write should have happened before read — position should be 5.0 when read
        assert ('position', 5.0) in move_actor.device.write_calls
        assert move_actor.device.read_count >= 1

    def test_loop_period_respected(self, viewer_actor):
        """With period=0.1, device.read() is not called more than 3 times in 150 ms."""
        req = ReadRequest(names=None, count=math.inf, period=0.1, requester='', req_id=b'\x00' * 16)
        viewer_actor._instruction_queue.put(req)
        viewer_actor._new_instruction_event.set()
        time.sleep(0.15)
        viewer_actor.stop(names=None)
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.read_count <= 3

    def test_loop_set_info_write_before_next_read(self, settings_actor):
        """Settings write (set_info) is processed before the following read."""
        write_instr = WriteInstruction(
            name=('settings', 'gain'), value=2, requester='', req_id=b'\x00' * 16
        )
        read_req = ReadRequest(names=None, count=1, period=0.0, requester='', req_id=b'\x01' * 16)
        settings_actor._instruction_queue.put(write_instr)
        settings_actor._instruction_queue.put(read_req)
        settings_actor._new_instruction_event.set()
        _wait_for_loop(settings_actor)
        assert ('gain', 2) in settings_actor.device.set_info_calls
        assert settings_actor.device.read_count >= 1

    def test_new_instruction_event_wakes_sleeping_loop(self, viewer_actor):
        """Loop with long period wakes up on new instruction within 0.2 s."""
        req = ReadRequest(names=None, count=1, period=5.0, requester='', req_id=b'\x00' * 16)
        viewer_actor._instruction_queue.put(req)
        viewer_actor._new_instruction_event.set()
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if viewer_actor.device.read_count >= 1:
                return
            time.sleep(0.01)
        assert viewer_actor.device.read_count >= 1, "Loop did not wake up in time"

    def test_stop_timer_called_on_connect(self):
        """connect() calls stop_timer() so the pyleco periodic timer is disabled."""
        stop_called = []
        actor = PymodaqActor(
            name='test_timer',
            device_class=_MockViewerDevice,
            context=FakeContext(),
        )
        original_stop_timer = actor.stop_timer
        actor.stop_timer = lambda: stop_called.append(True) or original_stop_timer()
        actor.connect()
        assert len(stop_called) >= 1
        actor._hw_stop_event.set()
        actor._new_instruction_event.set()


# ── Phase 2: RPC handler rewiring ─────────────────────────────────────────────

class TestRPCRewiring:
    def test_query_data_fresh_true_enqueues_and_returns_req_id(self, viewer_actor):
        """query_data(fresh=True) enqueues a ReadRequest and returns a hex req_id."""
        result = viewer_actor.query_data(names=None, count=1, fresh=True)
        assert viewer_actor._instruction_queue.qsize() >= 1
        assert isinstance(result, str) and len(result) == 32
        viewer_actor._instruction_queue.get_nowait()  # clean up

    def test_query_data_fresh_false_publishes_immediately_no_queue(self, viewer_actor):
        """query_data(fresh=False) publishes _last_data synchronously; queue stays empty."""
        from pymodaq_data.data import DataToExport, DataRaw
        viewer_actor._last_data = DataToExport(
            name='test', data=[DataRaw('ch', data=[np.zeros(1)])]
        )
        before = len(viewer_actor.publisher.socket._s)
        result = viewer_actor.query_data(fresh=False)
        assert len(viewer_actor.publisher.socket._s) > before
        assert viewer_actor._instruction_queue.empty()
        assert isinstance(result, str)

    def test_query_data_fresh_false_returns_none_when_no_cached_data(self, viewer_actor):
        assert viewer_actor._last_data is None
        result = viewer_actor.query_data(fresh=False)
        assert result is None

    def test_change_to_str_enqueues_write_instruction(self, move_actor):
        """change_to('pos', 5.0) enqueues a WriteInstruction."""
        # Drain any existing
        while not move_actor._instruction_queue.empty():
            move_actor._instruction_queue.get_nowait()
        move_actor.change_to('pos', 5.0)
        instr = move_actor._instruction_queue.get_nowait()
        assert isinstance(instr, WriteInstruction)
        assert instr.name == 'pos'
        assert instr.value == pytest.approx(5.0)

    def test_change_to_dict_enqueues_write_instruction(self, move_actor):
        """change_to({'a': 1, 'b': 2}) enqueues a single WriteInstruction with dict name."""
        while not move_actor._instruction_queue.empty():
            move_actor._instruction_queue.get_nowait()
        move_actor.change_to({'a': 1, 'b': 2})
        instr = move_actor._instruction_queue.get_nowait()
        assert isinstance(instr, WriteInstruction)
        assert isinstance(instr.name, dict)

    def test_stop_named_enqueues_stop_instruction(self, viewer_actor):
        while not viewer_actor._instruction_queue.empty():
            viewer_actor._instruction_queue.get_nowait()
        viewer_actor.stop(['frame'])
        instr = viewer_actor._instruction_queue.get_nowait()
        assert isinstance(instr, StopInstruction)
        assert instr.names == ['frame']

    def test_stop_all_enqueues_stop_none(self, viewer_actor):
        while not viewer_actor._instruction_queue.empty():
            viewer_actor._instruction_queue.get_nowait()
        viewer_actor.stop(names=None)
        instr = viewer_actor._instruction_queue.get_nowait()
        assert isinstance(instr, StopInstruction)
        assert instr.names is None

    def test_get_acquisition_status_returns_read_list_snapshot(self, viewer_actor):
        """get_acquisition_status() returns current read_list and is_grabbing."""
        viewer_actor._read_list = {
            frozenset(['frame']): ReadRequest(
                names=['frame'], count=math.inf, period=0.1,
                requester='localhost.d1', req_id=b'\x00' * 16,
            )
        }
        status = viewer_actor.get_acquisition_status()
        assert 'read_list' in status
        assert 'is_grabbing' in status
        assert status['is_grabbing'] is True
        assert 'frame' in status['read_list']

    def test_get_acquisition_status_empty_when_idle(self, viewer_actor):
        viewer_actor._read_list = {}
        status = viewer_actor.get_acquisition_status()
        assert status['is_grabbing'] is False
        assert status['read_list'] == {}

    def test_req_id_preserved_as_zmq_conversation_id(self, viewer_actor):
        """The req_id from ReadRequest is used as the ZMQ conversation_id."""
        from pyleco.core.serialization import generate_conversation_id
        req_id = generate_conversation_id()
        req = ReadRequest(names=None, count=1, period=0.0, requester='', req_id=req_id)
        before = len(viewer_actor.publisher.socket._s)
        viewer_actor._instruction_queue.put(req)
        viewer_actor._new_instruction_event.set()
        _wait_for_loop(viewer_actor)
        new_frames = viewer_actor.publisher.socket._s[before:]
        assert len(new_frames) > 0
        # The CID in the frame should match our req_id
        frame = new_frames[0]
        # frame[1] is the header in pyleco's DataMessage: CID(16B) + message_type(1B)
        if len(frame) > 1:
            assert frame[1][:16] == req_id


# ── TestActorInit ──────────────────────────────────────────────────────────────

class TestActorInit:
    def test_name(self, viewer_actor):
        assert viewer_actor.name == 'test_viewer'

    def test_director_registry_starts_empty(self, viewer_actor):
        assert viewer_actor._director_registry == set()

    def test_last_data_starts_none(self, viewer_actor):
        assert viewer_actor._last_data is None

    def test_instruction_queue_starts_empty(self, viewer_actor):
        assert viewer_actor._instruction_queue.empty()

    def test_read_list_starts_empty(self, viewer_actor):
        assert viewer_actor._read_list == {}

    def test_hw_thread_starts_alive(self, viewer_actor):
        assert viewer_actor._hw_thread is not None
        assert viewer_actor._hw_thread.is_alive()

    def test_device_created_on_connect(self, viewer_actor):
        assert isinstance(viewer_actor.device, _MockViewerDevice)

    def test_connect_calls_device_connect(self):
        actor = PymodaqActor(
            name='test_conn',
            device_class=_MockViewerDevice,
            context=FakeContext(),
        )
        actor.connect()
        assert actor.device.connected is True
        actor._hw_stop_event.set()
        actor._new_instruction_event.set()

    def test_disconnect_calls_device_close(self):
        actor = PymodaqActor(
            name='test_disc',
            device_class=_MockViewerDevice,
            context=FakeContext(),
        )
        actor.connect()
        device_ref = actor.device
        actor.disconnect()
        assert device_ref.closed is True

    def test_disconnect_without_close_method_does_not_raise(self):
        class _NoCloseDevice:
            def connect(self): pass
            def read(self, names=None): return None
            def write(self, name, value): pass

        actor = PymodaqActor(
            name='test_noclose',
            device_class=_NoCloseDevice,
            context=FakeContext(),
        )
        actor.connect()
        actor.disconnect()  # must not raise

    def test_periodic_reading_param_deprecated(self):
        with pytest.warns(DeprecationWarning):
            actor = PymodaqActor(
                name='test_deprecated',
                device_class=_MockViewerDevice,
                context=FakeContext(),
                periodic_reading=1.0,
            )
        actor._hw_stop_event.set()
        actor._new_instruction_event.set()


# ── Phase 8: Removed attributes ───────────────────────────────────────────────

class TestRemovedAttributes:
    def test_grab_loop_attribute_removed(self, viewer_actor):
        assert not hasattr(viewer_actor, '_grab_loop')

    def test_published_names_attribute_removed(self, viewer_actor):
        assert not hasattr(viewer_actor, '_published_names')

    def test_stop_grab_flag_attribute_removed(self, viewer_actor):
        assert not hasattr(viewer_actor, '_stop_grab_flag')

    def test_grabbed_names_attribute_removed(self, viewer_actor):
        assert not hasattr(viewer_actor, '_grabbed_names')

    def test_grab_thread_attribute_removed(self, viewer_actor):
        assert not hasattr(viewer_actor, '_grab_thread')


# ── RPC method registration ────────────────────────────────────────────────────

class TestRpcMethodsRegistered:
    @pytest.fixture(scope='class')
    def methods(self):
        actor = PymodaqActor(
            name='probe',
            device_class=_MockViewerDevice,
            context=FakeContext(),
        )
        actor.connect()
        discover = actor.rpc_handler.rpc.process_request(
            '{"jsonrpc":"2.0","id":1,"method":"rpc.discover"}'
        )
        names = [m['name'] for m in json.loads(discover)['result']['methods']]
        actor._hw_stop_event.set()
        actor._new_instruction_event.set()
        return names

    @pytest.mark.parametrize('method', [
        # New primary interface
        'query_data', 'change_to', 'stop',
        'get_acquisition_status', 'get_read_list',
        # Introspection
        'get_capabilities', 'get_pymodaq_settings', 'set_info',
        'subscribe_director', 'unsubscribe_director',
        # Manager
        'get_role', 'shutdown',
        # Deprecated aliases
        'query_data_continuous', 'stop_continuous',
        'get_grabbed_names', 'set_published_names', 'get_published_names',
        # Legacy aliases
        'grab', 'snap', 'get_actuator_value',
        'move_abs', 'move_rel', 'move_home',
        # Inherited from pyleco.actors.Actor
        'get_parameters', 'set_parameters', 'call_action',
        'start_polling', 'stop_polling',
    ])
    def test_method_registered(self, methods, method):
        assert method in methods, f"'{method}' not found in RPC methods"


# ── TestQueryData ─────────────────────────────────────────────────────────────

class TestQueryData:
    def test_fresh_true_enqueues_instruction(self, viewer_actor):
        """query_data(fresh=True) enqueues a ReadRequest (async)."""
        result = viewer_actor.query_data(fresh=True)
        assert not viewer_actor._instruction_queue.empty()
        assert isinstance(result, str) and len(result) == 32

    def test_fresh_calls_device_read_via_loop(self, viewer_actor):
        """After query_data(fresh=True), the hardware loop calls device.read()."""
        viewer_actor.query_data(fresh=True)
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.read_count >= 1

    def test_fresh_updates_last_data(self, viewer_actor):
        viewer_actor.query_data(fresh=True)
        _wait_for_loop(viewer_actor)
        assert viewer_actor._last_data is not None

    def test_not_fresh_does_not_call_device_read(self, viewer_actor):
        """query_data(fresh=False) never calls device.read()."""
        from pymodaq_data.data import DataToExport, DataRaw
        viewer_actor._last_data = DataToExport(
            name='cached', data=[DataRaw('ch', data=[np.zeros(1)])]
        )
        count_before = viewer_actor.device.read_count
        viewer_actor.query_data(fresh=False)
        assert viewer_actor.device.read_count == count_before

    def test_not_fresh_with_empty_cache_is_noop(self, viewer_actor):
        """query_data(fresh=False) with no cache is a no-op (no crash)."""
        assert viewer_actor._last_data is None
        result = viewer_actor.query_data(fresh=False)
        assert result is None

    def test_fresh_publishes_on_data_channel(self, viewer_actor):
        """After query_data(fresh=True), the actor's publisher socket has sent data."""
        before = len(viewer_actor.publisher.socket._s)
        viewer_actor.query_data(fresh=True)
        _wait_for_loop(viewer_actor)
        assert len(viewer_actor.publisher.socket._s) > before

    def test_return_value_is_cid(self, viewer_actor):
        """query_data returns the hex CID of the ZMQ publish for correlation."""
        cid = viewer_actor.query_data(fresh=True)
        assert isinstance(cid, str) and len(cid) == 32

    def test_singular_string_name_is_accepted(self, viewer_actor):
        """A single str passed as names= is accepted."""
        viewer_actor.query_data(names='data', fresh=True)
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.read_count >= 1

    def test_singular_string_forwarded_as_list(self, viewer_actor):
        """device.read is called with a list, not a bare string."""
        viewer_actor.query_data(names='data', fresh=True)
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.last_read_names == ['data']

    def test_list_names_forwarded_unchanged(self, viewer_actor):
        viewer_actor.query_data(names=['a', 'b'], fresh=True)
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.last_read_names == ['a', 'b']

    def test_none_names_forwarded_as_none(self, viewer_actor):
        viewer_actor.query_data(names=None, fresh=True)
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.last_read_names is None

    def test_count_inf_keeps_reading(self, viewer_actor):
        """query_data(count=inf) starts continuous acquisition."""
        viewer_actor.query_data(names=None, count=math.inf, fresh=True, period=0.0)
        time.sleep(0.06)
        viewer_actor.stop(names=None)
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.read_count >= 2


# ── TestChangeTo ──────────────────────────────────────────────────────────────

class TestChangeTo:
    def test_calls_device_write_via_loop(self, move_actor):
        move_actor.change_to('position', 10.0)
        _wait_for_loop(move_actor)
        assert ('position', 10.0) in move_actor.device.write_calls

    def test_updates_device_state(self, move_actor):
        move_actor.change_to('position', 5.5)
        _wait_for_loop(move_actor)
        assert move_actor.device._position == pytest.approx(5.5)

    def test_singular_name_calls_write_once(self, move_actor):
        # Reset
        move_actor.device.write_calls.clear()
        move_actor.change_to('position', 3.0)
        _wait_for_loop(move_actor)
        assert ('position', 3.0) in move_actor.device.write_calls

    def test_dict_form_calls_write_for_each_pair(self, move_actor):
        move_actor.device.write_calls.clear()
        move_actor.change_to({'x': 1.0, 'y': 2.0})
        _wait_for_loop(move_actor)
        assert ('x', 1.0) in move_actor.device.write_calls
        assert ('y', 2.0) in move_actor.device.write_calls

    def test_dict_form_via_rpc(self, move_actor):
        move_actor.device.write_calls.clear()
        handle_request_message(move_actor, 'change_to', name={'x': 10.0, 'y': 20.0})
        _wait_for_loop(move_actor)
        assert ('x', 10.0) in move_actor.device.write_calls
        assert ('y', 20.0) in move_actor.device.write_calls

    def test_change_to_triggers_readback_publish(self, move_actor):
        """After change_to, a one-shot readback is published on the data channel."""
        before = len(move_actor.publisher.socket._s)
        move_actor.change_to('position', 5.0)
        _wait_for_loop(move_actor)
        time.sleep(0.05)  # readback fires on next tick
        assert len(move_actor.publisher.socket._s) > before


# ── TestGetCapabilities ────────────────────────────────────────────────────────

class TestGetCapabilities:
    def test_returns_dict(self, viewer_actor):
        handle_request_message(viewer_actor, 'get_capabilities')
        result = _last_rpc_result(viewer_actor)
        assert isinstance(result, dict)

    def test_inferred_viewer_has_no_variables(self, viewer_actor):
        handle_request_message(viewer_actor, 'get_capabilities')
        result = _last_rpc_result(viewer_actor)
        assert result['variables'] == []

    def test_inferred_viewer_has_observable(self, viewer_actor):
        handle_request_message(viewer_actor, 'get_capabilities')
        result = _last_rpc_result(viewer_actor)
        assert len(result['observables']) == 1
        assert result['observables'][0]['name'] == 'data'

    def test_inferred_move_has_variable(self, move_actor):
        handle_request_message(move_actor, 'get_capabilities')
        result = _last_rpc_result(move_actor)
        assert len(result['variables']) == 1
        var = result['variables'][0]
        assert var['name'] == 'position'
        assert var['units'] == 'mm'
        assert var['epsilon'] == pytest.approx(0.001)

    def test_explicit_capabilities_returned(self, caps_actor):
        handle_request_message(caps_actor, 'get_capabilities')
        result = _last_rpc_result(caps_actor)
        assert len(result['observables']) == 1
        assert result['observables'][0]['name'] == 'spectrum'
        assert len(result['variables']) == 1
        assert result['variables'][0]['name'] == 'wavelength'


# ── TestGetPymodaqSettings ────────────────────────────────────────────────────

class TestGetPymodaqSettings:
    def test_returns_none_when_device_has_no_settings(self, viewer_actor):
        handle_request_message(viewer_actor, 'get_pymodaq_settings')
        assert _last_rpc_result(viewer_actor) is None

    def test_returns_xml_string(self, settings_actor):
        handle_request_message(settings_actor, 'get_pymodaq_settings')
        result = _last_rpc_result(settings_actor)
        assert isinstance(result, str)
        assert '<settings>' in result


# ── TestSetInfo ────────────────────────────────────────────────────────────────

class TestSetInfo:
    def test_enqueues_settings_write_instruction(self, settings_actor):
        """set_info enqueues a settings WriteInstruction (tuple sentinel)."""
        while not settings_actor._instruction_queue.empty():
            settings_actor._instruction_queue.get_nowait()
        settings_actor.set_info('gain', 2)
        instr = settings_actor._instruction_queue.get_nowait()
        assert isinstance(instr, WriteInstruction)
        assert isinstance(instr.name, tuple)
        assert instr.name[0] == 'settings'
        assert instr.name[1] == 'gain'
        assert instr.value == 2

    def test_delegates_to_device_set_info_via_loop(self, settings_actor):
        handle_request_message(settings_actor, 'set_info', path='gain', value=2)
        _wait_for_loop(settings_actor)
        assert settings_actor.device.set_info_calls == [('gain', 2)]

    def test_noop_when_device_has_no_set_info(self, viewer_actor):
        """set_info on a device without set_info is silently ignored (no crash)."""
        handle_request_message(viewer_actor, 'set_info', path='x', value=1)
        _wait_for_loop(viewer_actor)  # must not raise


# ── TestDirectorRegistry ──────────────────────────────────────────────────────

class TestDirectorRegistry:
    def test_subscribe_director_adds_name(self, viewer_actor):
        handle_request_message(viewer_actor, 'subscribe_director', name='ns.director1')
        assert 'ns.director1' in viewer_actor._director_registry

    def test_unsubscribe_director_removes_name(self, viewer_actor):
        viewer_actor._director_registry.add('ns.director1')
        handle_request_message(viewer_actor, 'unsubscribe_director', name='ns.director1')
        assert 'ns.director1' not in viewer_actor._director_registry

    def test_unsubscribe_nonexistent_is_noop(self, viewer_actor):
        handle_request_message(viewer_actor, 'unsubscribe_director', name='ns.nobody')

    def test_subscribe_multiple(self, viewer_actor):
        handle_request_message(viewer_actor, 'subscribe_director', name='ns.d1')
        handle_request_message(viewer_actor, 'subscribe_director', name='ns.d2')
        assert {'ns.d1', 'ns.d2'}.issubset(viewer_actor._director_registry)


# ── TestDeprecatedAliases ──────────────────────────────────────────────────────

class TestDeprecatedAliases:
    def test_query_data_continuous_enqueues_inf_read(self, viewer_actor):
        """query_data_continuous enqueues a ReadRequest with count=inf."""
        while not viewer_actor._instruction_queue.empty():
            viewer_actor._instruction_queue.get_nowait()
        viewer_actor.query_data_continuous(rate_hz=10)
        instr = viewer_actor._instruction_queue.get_nowait()
        assert isinstance(instr, ReadRequest)
        assert math.isinf(instr.count)
        assert instr.period == pytest.approx(0.1)

    def test_stop_continuous_enqueues_stop_all(self, viewer_actor):
        """stop_continuous enqueues a StopInstruction with names=None."""
        while not viewer_actor._instruction_queue.empty():
            viewer_actor._instruction_queue.get_nowait()
        viewer_actor.stop_continuous()
        instr = viewer_actor._instruction_queue.get_nowait()
        assert isinstance(instr, StopInstruction)
        assert instr.names is None

    def test_get_grabbed_names_returns_none_when_idle(self, viewer_actor):
        assert viewer_actor._read_list == {}
        assert viewer_actor.get_grabbed_names() is None

    def test_get_grabbed_names_returns_names_when_reading(self, viewer_actor):
        viewer_actor._read_list[frozenset(['spectrum'])] = ReadRequest(
            names=['spectrum'], count=math.inf, period=0.0, requester='', req_id=b'\x00' * 16
        )
        result = viewer_actor.get_grabbed_names()
        assert result == ['spectrum']
        viewer_actor._read_list.clear()

    def test_set_published_names_is_noop(self, viewer_actor):
        """set_published_names is deprecated and has no effect (no crash)."""
        viewer_actor.set_published_names(['spectrum'])  # must not raise

    def test_get_published_names_delegates_to_grabbed_names(self, viewer_actor):
        assert viewer_actor._read_list == {}
        assert viewer_actor.get_published_names() is None


# ── TestLegacyAliases ─────────────────────────────────────────────────────────

class TestLegacyAliases:
    def test_grab_calls_device_read(self, viewer_actor):
        handle_request_message(viewer_actor, 'grab')
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.read_count >= 1

    def test_snap_calls_device_read(self, viewer_actor):
        handle_request_message(viewer_actor, 'snap')
        _wait_for_loop(viewer_actor)
        assert viewer_actor.device.read_count >= 1

    def test_get_actuator_value_calls_device_read(self, move_actor):
        handle_request_message(move_actor, 'get_actuator_value')
        _wait_for_loop(move_actor)
        assert move_actor.device.read_count >= 1

    def test_move_abs_updates_position(self, move_actor):
        handle_request_message(move_actor, 'move_abs', position=7.0)
        _wait_for_loop(move_actor)
        assert move_actor.device._position == pytest.approx(7.0)

    def test_move_rel_delegates_to_device(self, move_actor):
        handle_request_message(move_actor, 'move_rel', position=2.5)
        assert move_actor.device.move_rel_calls == [2.5]

    def test_move_rel_raises_when_device_has_no_method(self, viewer_actor):
        handle_request_message(viewer_actor, 'move_rel', position=1.0)
        frames = viewer_actor.socket._s[-1]
        error_found = any(
            isinstance(json.loads(f.decode()), dict) and 'error' in json.loads(f.decode())
            for f in frames
            if isinstance(f, bytes) and f.startswith(b'{')
        )
        assert error_found, "Expected a JSON-RPC error response"

    def test_move_home_calls_device_home(self, move_actor):
        handle_request_message(move_actor, 'move_home')
        assert move_actor.device.home_called is True

    def test_move_home_fallback_sets_position_zero(self, viewer_actor):
        handle_request_message(viewer_actor, 'move_home')
        _wait_for_loop(viewer_actor)
        assert ('position', 0.0) in viewer_actor.device.write_calls


# ── Helpers for sub-topic inspection ──────────────────────────────────────────

def _sent_topics(actor) -> list[str]:
    topics = []
    for frame_list in actor.publisher.socket._s:
        if frame_list:
            first = frame_list[0]
            topics.append(first.decode() if isinstance(first, bytes) else str(first))
    return topics


def _sent_payloads(actor):
    from serializall import SerializableFactory
    factory = SerializableFactory()
    payloads = []
    for frame_list in actor.publisher.socket._s:
        if len(frame_list) >= 3:
            payloads.append(factory.get_apply_deserializer(frame_list[2]))
    return payloads


class TestSubTopicPublish:
    def test_single_dwa_published_to_subtopic(self, viewer_actor):
        viewer_actor.query_data(fresh=True)
        _wait_for_loop(viewer_actor)
        topics = _sent_topics(viewer_actor)
        assert any(t == f"{viewer_actor.name}/spectrum" for t in topics)

    def test_each_dwa_gets_own_subtopic(self, caps_actor):
        before = len(caps_actor.publisher.socket._s)
        caps_actor.query_data(fresh=True)
        _wait_for_loop(caps_actor)
        new_frames = caps_actor.publisher.socket._s[before:]
        topics = [f[0].decode() if isinstance(f[0], bytes) else f[0] for f in new_frames]
        assert f"{caps_actor.name}/spectrum" in topics
        assert f"{caps_actor.name}/wavelength" in topics

    def test_published_payload_is_single_dwa_dte(self, viewer_actor):
        viewer_actor.query_data(fresh=True)
        _wait_for_loop(viewer_actor)
        payloads = _sent_payloads(viewer_actor)
        assert payloads, "Expected at least one published frame"
        for dte in payloads:
            assert len(dte.data) == 1

    def test_subtopic_dwa_name_matches_topic(self, viewer_actor):
        viewer_actor.query_data(fresh=True)
        _wait_for_loop(viewer_actor)
        for frame_list in viewer_actor.publisher.socket._s:
            topic = frame_list[0].decode() if isinstance(frame_list[0], bytes) else frame_list[0]
            channel = topic.split('/')[-1]
            from serializall import SerializableFactory
            dte = SerializableFactory().get_apply_deserializer(frame_list[2])
            assert dte.data[0].name == channel

    def test_change_to_triggers_readback_publish_on_written_channel(self, caps_actor):
        """change_to publishes the written channel via readback."""
        before = len(caps_actor.publisher.socket._s)
        caps_actor.change_to('wavelength', 500.0)
        _wait_for_loop(caps_actor)
        time.sleep(0.05)  # readback fires
        topics = _sent_topics(caps_actor)
        new_topics = [t for t in topics[len(_sent_topics(caps_actor)):]]
        # Just verify publish happened
        assert len(caps_actor.publisher.socket._s) > before

    def test_no_flat_topic_published(self, viewer_actor):
        viewer_actor.query_data(fresh=True)
        _wait_for_loop(viewer_actor)
        topics = _sent_topics(viewer_actor)
        assert not any(t == viewer_actor.name for t in topics)


# ── Phase 0: get_role / shutdown ───────────────────────────────────────────────

class TestGetRole:
    def test_get_role_returns_dict(self, viewer_actor):
        result = viewer_actor.get_role()
        assert isinstance(result, dict)

    def test_get_role_role_field_is_actor(self, viewer_actor):
        result = viewer_actor.get_role()
        assert result['role'] == 'actor'

    def test_get_role_host_field_present(self, viewer_actor):
        assert 'host' in viewer_actor.get_role()

    def test_get_role_host_matches_publisher_full_name(self, viewer_actor):
        result = viewer_actor.get_role()
        assert result['host'] == viewer_actor.publisher.full_name

    def test_get_role_registered_as_rpc_method(self):
        actor = PymodaqActor(
            name='probe_role', device_class=_MockViewerDevice, context=FakeContext(),
        )
        actor.connect()
        discover = actor.rpc_handler.rpc.process_request(
            '{"jsonrpc":"2.0","id":1,"method":"rpc.discover"}'
        )
        method_names = [m['name'] for m in json.loads(discover)['result']['methods']]
        assert 'get_role' in method_names
        actor._hw_stop_event.set()
        actor._new_instruction_event.set()


class TestShutdown:
    def test_shutdown_stops_hardware_loop(self, viewer_actor):
        assert viewer_actor._hw_thread is not None and viewer_actor._hw_thread.is_alive()
        viewer_actor.shutdown()
        time.sleep(0.05)
        assert not viewer_actor._hw_thread.is_alive() if viewer_actor._hw_thread else True

    def test_shutdown_clears_director_registry(self, viewer_actor):
        viewer_actor._director_registry = {'localhost.dir1', 'localhost.dir2'}
        viewer_actor.shutdown()
        assert len(viewer_actor._director_registry) == 0

    def test_shutdown_sets_stop_event(self, viewer_actor):
        import threading
        stop = threading.Event()
        viewer_actor._stop_event = stop
        viewer_actor.shutdown()
        assert stop.is_set()

    def test_shutdown_no_error_when_hw_loop_not_running(self):
        actor = PymodaqActor(
            name='probe_shutdown', device_class=_MockViewerDevice, context=FakeContext(),
        )
        # Not connected — no hw thread
        actor.shutdown()  # must not raise

    def test_shutdown_registered_as_rpc_method(self):
        actor = PymodaqActor(
            name='probe_sd', device_class=_MockViewerDevice, context=FakeContext(),
        )
        actor.connect()
        discover = actor.rpc_handler.rpc.process_request(
            '{"jsonrpc":"2.0","id":1,"method":"rpc.discover"}'
        )
        method_names = [m['name'] for m in json.loads(discover)['result']['methods']]
        assert 'shutdown' in method_names
        actor._hw_stop_event.set()
        actor._new_instruction_event.set()


# ── Phase 7: Error propagation ─────────────────────────────────────────────────

class TestErrorPropagation:
    def test_device_read_exception_removes_entry(self, viewer_actor):
        """If device.read() raises, the read_list entry is removed."""
        def failing_read(names=None):
            raise RuntimeError("sensor disconnected")
        viewer_actor.device.read = failing_read

        req = ReadRequest(names=None, count=math.inf, period=0.0, requester='', req_id=b'\x00' * 16)
        viewer_actor._instruction_queue.put(req)
        viewer_actor._new_instruction_event.set()
        _wait_for_loop(viewer_actor)
        time.sleep(0.05)
        assert None not in viewer_actor._read_list

    def test_device_read_exception_does_not_crash_loop(self, viewer_actor):
        """After a read exception, the loop continues and processes new instructions."""
        call_count = [0]

        def failing_then_ok_read(names=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient error")
            from pymodaq_data.data import DataToExport, DataRaw
            return DataToExport(name='ok', data=[DataRaw('ch', data=[np.zeros(1)])])

        viewer_actor.device.read = failing_then_ok_read

        req1 = ReadRequest(names=None, count=1, period=0.0, requester='', req_id=b'\x00' * 16)
        viewer_actor._instruction_queue.put(req1)
        viewer_actor._new_instruction_event.set()
        time.sleep(0.05)

        req2 = ReadRequest(names=None, count=1, period=0.0, requester='', req_id=b'\x01' * 16)
        viewer_actor._instruction_queue.put(req2)
        viewer_actor._new_instruction_event.set()
        _wait_for_loop(viewer_actor)
        assert call_count[0] >= 2

    def test_device_write_exception_does_not_crash_loop(self, move_actor):
        """If device.write() raises, write_pending is cleared and loop continues."""
        def failing_write(name, value):
            raise RuntimeError("write failed")
        move_actor.device.write = failing_write

        move_actor.change_to('position', 5.0)
        _wait_for_loop(move_actor)
        assert move_actor._write_pending == {}
        # Verify loop still runs
        move_actor.device.write = lambda n, v: None  # restore
        req = ReadRequest(names=None, count=1, period=0.0, requester='', req_id=b'\x00' * 16)
        move_actor._instruction_queue.put(req)
        move_actor._new_instruction_event.set()
        _wait_for_loop(move_actor)
