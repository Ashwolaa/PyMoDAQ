"""Tests for pymodaq.utils.leco.actor.PymodaqActor.

Pure Python — no Qt, no LECO network, no real hardware.
Uses pyleco's FakeContext and handle_request_message utilities.
"""
import json

import numpy as np
import pytest

from pyleco.test import FakeContext, handle_request_message

from pymodaq.utils.leco.actor import PymodaqActor
from pymodaq.control_modules.capabilities import (
    Capabilities,
    ContinuousVariable,
    Observable,
    Variable,
)

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


# ── Mock devices ───────────────────────────────────────────────────────────────

class _MockViewerDevice:
    """Minimal pure-Python mock of a read-only detector plugin."""

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
    """Minimal pure-Python mock of an actuator plugin with a single position axis."""

    _controller_units = 'mm'
    _axis_names = None
    _epsilons = 0.001

    def __init__(self):
        from pymodaq_data.data import DataToExport, DataRaw
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
    """Mock device that exposes get_settings / set_info."""

    def __init__(self):
        self._xml = '<settings><param name="gain" value="1"/></settings>'
        self.set_info_calls: list = []
        self.write_calls: list = []

    def connect(self): pass
    def close(self): pass

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        return DataToExport(name='s', data=[DataRaw('ch', data=[np.zeros(1)])])

    def write(self, name, value):
        self.write_calls.append((name, value))

    def get_settings(self) -> str:
        return self._xml

    def set_info(self, path: str, value):
        self.set_info_calls.append((path, value))


class _MockDeviceWithCapabilities:
    """Mock device with an explicit Capabilities declaration."""

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
    return actor


@pytest.fixture
def move_actor():
    actor = PymodaqActor(
        name='test_move',
        device_class=_MockMoveDevice,
        context=FakeContext(),
    )
    actor.connect()
    return actor


@pytest.fixture
def settings_actor():
    actor = PymodaqActor(
        name='test_settings',
        device_class=_MockDeviceWithSettings,
        context=FakeContext(),
    )
    actor.connect()
    return actor


@pytest.fixture
def caps_actor():
    actor = PymodaqActor(
        name='test_caps',
        device_class=_MockDeviceWithCapabilities,
        context=FakeContext(),
    )
    actor.connect()
    return actor


# ── Test classes ───────────────────────────────────────────────────────────────

class TestActorInit:
    def test_name(self, viewer_actor):
        assert viewer_actor.name == 'test_viewer'

    def test_director_registry_starts_empty(self, viewer_actor):
        assert viewer_actor._director_registry == set()

    def test_last_data_starts_none(self, viewer_actor):
        assert viewer_actor._last_data is None

    def test_stop_grab_flag_starts_false(self, viewer_actor):
        assert viewer_actor._stop_grab_flag is False

    def test_device_created_on_connect(self, viewer_actor):
        assert isinstance(viewer_actor.device, _MockViewerDevice)

    def test_connect_calls_device_connect(self):
        """PymodaqActor.connect() must call device.connect() after instantiation."""
        actor = PymodaqActor(
            name='test_conn',
            device_class=_MockViewerDevice,
            context=FakeContext(),
        )
        actor.connect()
        assert actor.device.connected is True

    def test_disconnect_calls_device_close(self):
        """PymodaqActor.disconnect() must call device.close() instead of pymeasure adapter."""
        actor = PymodaqActor(
            name='test_disc',
            device_class=_MockViewerDevice,
            context=FakeContext(),
        )
        actor.connect()
        device_ref = actor.device   # keep reference before disconnect deletes it
        actor.disconnect()
        assert device_ref.closed is True

    def test_disconnect_without_close_method_does_not_raise(self):
        """Disconnect is safe even if the device has no close() method."""

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
        actor.disconnect()   # must not raise


class TestRpcMethodsRegistered:
    """Verify that all expected RPC method names are registered on the actor."""

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
        import json
        return json.loads(discover)['result']['methods']

    @pytest.mark.parametrize('method', [
        'query_data', 'change_to',
        'get_capabilities', 'get_pymodaq_settings', 'set_info',
        'subscribe_director', 'unsubscribe_director',
        'query_data_continuous', 'stop_continuous',
        'set_published_names', 'get_published_names', 'get_grabbed_names',
        # Legacy aliases
        'grab', 'snap', 'get_actuator_value',
        'move_abs', 'move_rel', 'move_home',
        # Inherited from pyleco.actors.Actor
        'get_parameters', 'set_parameters', 'call_action',
        'start_polling', 'stop_polling',
    ])
    def test_method_registered(self, methods, method):
        method_names = [m['name'] for m in methods]
        assert method in method_names, f"'{method}' not found in RPC methods"


class TestQueryData:
    def test_fresh_calls_device_read(self, viewer_actor):
        handle_request_message(viewer_actor, 'query_data', fresh=True)
        assert viewer_actor.device.read_count == 1

    def test_fresh_updates_last_data(self, viewer_actor):
        handle_request_message(viewer_actor, 'query_data', fresh=True)
        assert viewer_actor._last_data is not None

    def test_not_fresh_does_not_call_device_read(self, viewer_actor):
        # Prime cache first
        handle_request_message(viewer_actor, 'query_data', fresh=True)
        count_after_prime = viewer_actor.device.read_count
        handle_request_message(viewer_actor, 'query_data', fresh=False)
        assert viewer_actor.device.read_count == count_after_prime

    def test_not_fresh_with_empty_cache_is_noop(self, viewer_actor):
        """query_data(fresh=False) with no cache is a no-op (no crash)."""
        assert viewer_actor._last_data is None
        handle_request_message(viewer_actor, 'query_data', fresh=False)  # must not raise

    def test_fresh_publishes_on_data_channel(self, viewer_actor):
        """After query_data(fresh=True), the actor's publisher socket has sent data."""
        before = len(viewer_actor.publisher.socket._s)
        handle_request_message(viewer_actor, 'query_data', fresh=True)
        after = len(viewer_actor.publisher.socket._s)
        assert after > before

    def test_return_value_is_cid(self, viewer_actor):
        """query_data returns the hex CID of the ZMQ publish for correlation."""
        handle_request_message(viewer_actor, 'query_data', fresh=True)
        cid = _last_rpc_result(viewer_actor)
        assert isinstance(cid, str) and len(cid) == 32

    def test_stop_continuous_suppresses_read_publish(self, viewer_actor):
        viewer_actor._stop_grab_flag = True
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)
        assert viewer_actor.device.read_count == 0

    # Singular / plural name acceptance
    def test_singular_string_name_is_accepted(self, viewer_actor):
        """A single str passed as names= is wrapped in a list for device.read."""
        viewer_actor.query_data(names='data', fresh=True)
        assert viewer_actor.device.read_count == 1

    def test_singular_string_forwarded_as_list(self, viewer_actor):
        """device.read is called with a list, not a bare string."""
        viewer_actor.query_data(names='data', fresh=True)
        last_names = viewer_actor.device.last_read_names
        assert last_names == ['data']

    def test_list_names_forwarded_unchanged(self, viewer_actor):
        viewer_actor.query_data(names=['a', 'b'], fresh=True)
        assert viewer_actor.device.last_read_names == ['a', 'b']

    def test_none_names_forwarded_as_none(self, viewer_actor):
        viewer_actor.query_data(names=None, fresh=True)
        assert viewer_actor.device.last_read_names is None


class TestChangeTo:
    def test_calls_device_write(self, move_actor):
        handle_request_message(move_actor, 'change_to', name='position', value=10.0)
        assert move_actor.device.write_calls == [('position', 10.0)]

    def test_updates_device_state(self, move_actor):
        handle_request_message(move_actor, 'change_to', name='position', value=5.5)
        assert move_actor.device._position == pytest.approx(5.5)

    # Singular / plural name acceptance
    def test_singular_name_calls_write_once(self, move_actor):
        move_actor.change_to('position', 3.0)
        assert move_actor.device.write_calls == [('position', 3.0)]

    def test_dict_form_calls_write_for_each_pair(self, move_actor):
        """Dict form writes each name/value pair."""
        move_actor.change_to({'x': 1.0, 'y': 2.0})
        assert ('x', 1.0) in move_actor.device.write_calls
        assert ('y', 2.0) in move_actor.device.write_calls

    def test_dict_form_via_rpc(self, move_actor):
        handle_request_message(move_actor, 'change_to', name={'x': 10.0, 'y': 20.0})
        assert ('x', 10.0) in move_actor.device.write_calls
        assert ('y', 20.0) in move_actor.device.write_calls


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


class TestGetPymodaqSettings:
    def test_returns_none_when_device_has_no_settings(self, viewer_actor):
        handle_request_message(viewer_actor, 'get_pymodaq_settings')
        assert _last_rpc_result(viewer_actor) is None

    def test_returns_xml_string(self, settings_actor):
        handle_request_message(settings_actor, 'get_pymodaq_settings')
        result = _last_rpc_result(settings_actor)
        assert isinstance(result, str)
        assert '<settings>' in result


class TestSetInfo:
    def test_delegates_to_device_set_info(self, settings_actor):
        handle_request_message(settings_actor, 'set_info', path='gain', value=2)
        assert settings_actor.device.set_info_calls == [('gain', 2)]

    def test_noop_when_device_has_no_set_info(self, viewer_actor):
        """set_info on a device without set_info is silently ignored."""
        handle_request_message(viewer_actor, 'set_info', path='x', value=1)  # must not raise


class TestDirectorRegistry:
    def test_subscribe_director_adds_name(self, viewer_actor):
        handle_request_message(viewer_actor, 'subscribe_director', name='ns.director1')
        assert 'ns.director1' in viewer_actor._director_registry

    def test_unsubscribe_director_removes_name(self, viewer_actor):
        viewer_actor._director_registry.add('ns.director1')
        handle_request_message(viewer_actor, 'unsubscribe_director', name='ns.director1')
        assert 'ns.director1' not in viewer_actor._director_registry

    def test_unsubscribe_nonexistent_is_noop(self, viewer_actor):
        handle_request_message(viewer_actor, 'unsubscribe_director', name='ns.nobody')  # no raise

    def test_subscribe_multiple(self, viewer_actor):
        handle_request_message(viewer_actor, 'subscribe_director', name='ns.d1')
        handle_request_message(viewer_actor, 'subscribe_director', name='ns.d2')
        assert {'ns.d1', 'ns.d2'}.issubset(viewer_actor._director_registry)


class TestPublishedNames:
    def test_published_names_default_is_none(self, viewer_actor):
        assert viewer_actor._published_names is None

    def test_set_published_names_via_rpc(self, viewer_actor):
        handle_request_message(viewer_actor, 'set_published_names', names=['spectrum'])
        assert viewer_actor._published_names == {'spectrum'}

    def test_set_published_names_none_removes_filter(self, viewer_actor):
        viewer_actor._published_names = {'spectrum'}
        handle_request_message(viewer_actor, 'set_published_names', names=None)
        assert viewer_actor._published_names is None

    def test_set_published_names_empty_list(self, viewer_actor):
        handle_request_message(viewer_actor, 'set_published_names', names=[])
        assert viewer_actor._published_names == set()

    def test_get_published_names_none_when_no_filter(self, viewer_actor):
        handle_request_message(viewer_actor, 'get_published_names')
        assert _last_rpc_result(viewer_actor) is None

    def test_get_published_names_returns_sorted_list(self, viewer_actor):
        viewer_actor._published_names = {'b', 'a'}
        handle_request_message(viewer_actor, 'get_published_names')
        result = _last_rpc_result(viewer_actor)
        assert result == ['a', 'b']

    def test_read_publish_skipped_when_published_names_empty(self, viewer_actor):
        """Periodic timer does nothing when _published_names is explicitly empty."""
        viewer_actor._published_names = set()
        before = len(viewer_actor.publisher.socket._s)
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)
        assert len(viewer_actor.publisher.socket._s) == before
        assert viewer_actor.device.read_count == 0

    def test_read_publish_uses_published_names_filter(self, viewer_actor):
        """Periodic timer passes _published_names to device.read()."""
        viewer_actor._published_names = {'spectrum'}
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)
        assert viewer_actor.device.last_read_names == ['spectrum']

    def test_read_publish_all_when_no_filter(self, viewer_actor):
        """Periodic timer passes None to device.read() when no filter set."""
        assert viewer_actor._published_names is None
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)
        assert viewer_actor.device.last_read_names is None


class TestGrabbedNames:
    def test_grabbed_names_default_is_none(self, viewer_actor):
        assert viewer_actor._grabbed_names is None

    def test_get_grabbed_names_rpc_returns_none_when_not_grabbing(self, viewer_actor):
        handle_request_message(viewer_actor, 'get_grabbed_names')
        assert _last_rpc_result(viewer_actor) is None

    def test_query_data_continuous_sets_grabbed_names_from_published(self, viewer_actor):
        viewer_actor._published_names = {'spectrum', 'intensity'}
        viewer_actor.query_data_continuous()
        assert viewer_actor._grabbed_names == {'spectrum', 'intensity'}
        viewer_actor.stop_continuous()

    def test_query_data_continuous_grabbed_names_none_when_no_filter(self, viewer_actor):
        """When _published_names is None (no filter), _grabbed_names is also None."""
        assert viewer_actor._published_names is None
        viewer_actor.query_data_continuous()
        assert viewer_actor._grabbed_names is None
        viewer_actor.stop_continuous()

    def test_stop_continuous_clears_grabbed_names(self, viewer_actor):
        viewer_actor._published_names = {'spectrum'}
        viewer_actor.query_data_continuous()
        viewer_actor.stop_continuous()
        assert viewer_actor._grabbed_names is None

    def test_get_grabbed_names_rpc_returns_sorted_list_while_grabbing(self, viewer_actor):
        viewer_actor._published_names = {'b', 'a'}
        viewer_actor.query_data_continuous()
        handle_request_message(viewer_actor, 'get_grabbed_names')
        result = _last_rpc_result(viewer_actor)
        assert result == ['a', 'b']
        viewer_actor.stop_continuous()


class TestLegacyAliases:
    def test_grab_calls_device_read(self, viewer_actor):
        handle_request_message(viewer_actor, 'grab')
        assert viewer_actor.device.read_count == 1

    def test_snap_calls_device_read(self, viewer_actor):
        handle_request_message(viewer_actor, 'snap')
        assert viewer_actor.device.read_count == 1

    def test_get_actuator_value_calls_device_read(self, move_actor):
        handle_request_message(move_actor, 'get_actuator_value')
        assert move_actor.device.read_count == 1

    def test_stop_continuous_sets_flag(self, viewer_actor):
        handle_request_message(viewer_actor, 'stop_continuous')
        assert viewer_actor._stop_grab_flag is True
        assert viewer_actor._grab_thread is None  # no thread was running

    def test_grab_clears_stop_flag(self, viewer_actor):
        viewer_actor._stop_grab_flag = True
        handle_request_message(viewer_actor, 'grab')
        assert viewer_actor._stop_grab_flag is False

    def test_move_abs_updates_position(self, move_actor):
        handle_request_message(move_actor, 'move_abs', position=7.0)
        assert move_actor.device._position == pytest.approx(7.0)

    def test_move_rel_delegates_to_device(self, move_actor):
        handle_request_message(move_actor, 'move_rel', position=2.5)
        assert move_actor.device.move_rel_calls == [2.5]

    def test_move_rel_raises_when_device_has_no_method(self, viewer_actor):
        """move_rel on a device without move_rel raises NotImplementedError."""
        from pyleco.json_utils.json_objects import ErrorResponse
        viewer_actor.device._position = 0.0
        # The error is caught by pyleco's RPC layer and returned as a JSON-RPC error
        handle_request_message(viewer_actor, 'move_rel', position=1.0)
        frames = viewer_actor.socket._s[-1]
        error_found = False
        for frame in frames:
            try:
                parsed = json.loads(frame.decode())
                if isinstance(parsed, dict) and 'error' in parsed:
                    error_found = True
                    break
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        assert error_found, "Expected a JSON-RPC error response for move_rel without device support"

    def test_move_home_calls_device_home(self, move_actor):
        handle_request_message(move_actor, 'move_home')
        assert move_actor.device.home_called is True

    def test_move_home_fallback_sets_position_zero(self, viewer_actor):
        """move_home on a device without home() writes position=0."""
        handle_request_message(viewer_actor, 'move_home')
        # No crash; write was called with position=0.0
        assert viewer_actor.device.write_calls == [('position', 0.0)]


class TestContinuousGrab:
    """Tests for query_data_continuous / stop_continuous continuous acquisition loop."""

    def test_query_data_continuous_spawns_thread(self, viewer_actor):
        viewer_actor.query_data_continuous()
        assert viewer_actor._grab_thread is not None
        assert viewer_actor._grab_thread.is_alive()
        viewer_actor.stop_continuous()

    def test_query_data_continuous_clears_stop_flag(self, viewer_actor):
        viewer_actor._stop_grab_flag = True
        viewer_actor.query_data_continuous()
        assert viewer_actor._stop_grab_flag is False
        viewer_actor.stop_continuous()

    def test_stop_continuous_sets_flag_and_joins(self, viewer_actor):
        viewer_actor.query_data_continuous()
        viewer_actor.stop_continuous()
        assert viewer_actor._stop_grab_flag is True
        assert viewer_actor._grab_thread is None

    def test_stop_continuous_without_start_is_safe(self, viewer_actor):
        """stop_continuous() when no grab is running must not raise."""
        viewer_actor.stop_continuous()  # no-op

    def test_query_data_continuous_is_idempotent(self, viewer_actor):
        """A second query_data_continuous() while the loop is alive does not restart it."""
        viewer_actor.query_data_continuous()
        first_thread = viewer_actor._grab_thread
        viewer_actor.query_data_continuous()   # second call — idempotent
        assert viewer_actor._grab_thread is first_thread   # same thread, not replaced
        viewer_actor.stop_continuous()

    def test_grab_loop_publishes_data(self, viewer_actor):
        """The grab loop must publish at least one ZMQ frame."""
        before = len(viewer_actor.publisher.socket._s)
        viewer_actor.query_data_continuous()
        import time; time.sleep(0.05)   # let loop spin at least once
        viewer_actor.stop_continuous()
        assert len(viewer_actor.publisher.socket._s) > before

    def test_grab_loop_updates_last_data(self, viewer_actor):
        viewer_actor.query_data_continuous()
        import time; time.sleep(0.05)
        viewer_actor.stop_continuous()
        assert viewer_actor._last_data is not None

    def test_stop_continuous_via_rpc(self, viewer_actor):
        viewer_actor.query_data_continuous()
        handle_request_message(viewer_actor, 'stop_continuous')
        assert viewer_actor._stop_grab_flag is True
        assert viewer_actor._grab_thread is None

    def test_query_data_continuous_via_rpc(self, viewer_actor):
        handle_request_message(viewer_actor, 'query_data_continuous')
        assert viewer_actor._grab_thread is not None
        assert viewer_actor._grab_thread.is_alive()
        viewer_actor.stop_continuous()

    def test_query_data_continuous_rate_hz_limits_calls(self, viewer_actor):
        """With rate_hz=20 the loop must not call device.read more than ~5x in 100 ms."""
        viewer_actor.query_data_continuous(rate_hz=20)
        import time; time.sleep(0.15)
        viewer_actor.stop_continuous()
        # 20 Hz for 150 ms → ~3 frames; allow up to 6 for timing jitter
        assert viewer_actor.device.read_count <= 6

    def test_grab_loop_stops_on_device_exception(self, viewer_actor):
        """If device.read() raises, the loop exits cleanly without crashing the actor."""
        call_count = [0]
        def failing_read(names=None):
            call_count[0] += 1
            raise RuntimeError("sensor disconnected")
        viewer_actor.device.read = failing_read
        viewer_actor.query_data_continuous()
        import time; time.sleep(0.05)
        assert not viewer_actor._grab_thread.is_alive()
        viewer_actor._grab_thread = None  # clean up


class TestReadPublish:
    def test_read_publish_calls_device_read(self, viewer_actor):
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)
        assert viewer_actor.device.read_count == 1

    def test_read_publish_updates_cache(self, viewer_actor):
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)
        assert viewer_actor._last_data is not None

    def test_read_publish_publishes_on_data_channel(self, viewer_actor):
        before = len(viewer_actor.publisher.socket._s)
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)
        after = len(viewer_actor.publisher.socket._s)
        assert after > before

    def test_read_publish_skipped_when_stop_flag(self, viewer_actor):
        viewer_actor._stop_grab_flag = True
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)
        assert viewer_actor.device.read_count == 0
        assert viewer_actor._last_data is None

    def test_read_publish_handles_device_exception_gracefully(self, viewer_actor):
        """A crash in device.read() must not propagate — actor continues."""
        def bad_read(names=None):
            raise RuntimeError("hardware exploded")
        viewer_actor.device.read = bad_read
        viewer_actor.read_publish(viewer_actor.device, viewer_actor.publisher)  # must not raise


# ── Helpers for sub-topic inspection ──────────────────────────────────────────

def _sent_topics(actor) -> list[str]:
    """Return the ZMQ topic (first frame, decoded) for every publish call made."""
    topics = []
    for frame_list in actor.publisher.socket._s:
        if frame_list:
            first = frame_list[0]
            topics.append(first.decode() if isinstance(first, bytes) else str(first))
    return topics


def _sent_payloads(actor):
    """Return deserialized DataToExport objects from all publish calls."""
    from serializall import SerializableFactory
    factory = SerializableFactory()
    payloads = []
    for frame_list in actor.publisher.socket._s:
        if len(frame_list) >= 3:
            payloads.append(factory.get_apply_deserializer(frame_list[2]))
    return payloads


class TestSubTopicPublish:
    """B1 — actor publishes each DWA to its own sub-topic."""

    def test_single_dwa_published_to_subtopic(self, viewer_actor):
        """`query_data` on a single-DWA device sends to '{name}/spectrum'."""
        viewer_actor.query_data(fresh=True)
        topics = _sent_topics(viewer_actor)
        assert any(t == f"{viewer_actor.name}/spectrum" for t in topics)

    def test_each_dwa_gets_own_subtopic(self, caps_actor):
        """A device with two DWAs (spectrum + wavelength) sends two frames on distinct topics."""
        # caps_actor device has read() returning spectrum + wavelength
        before = len(caps_actor.publisher.socket._s)
        caps_actor.query_data(fresh=True)
        new_frames = caps_actor.publisher.socket._s[before:]
        topics = [f[0].decode() if isinstance(f[0], bytes) else f[0] for f in new_frames]
        assert f"{caps_actor.name}/spectrum" in topics
        assert f"{caps_actor.name}/wavelength" in topics

    def test_published_payload_is_single_dwa_dte(self, viewer_actor):
        """Each frame payload deserializes to a DataToExport with exactly one DWA."""
        viewer_actor.query_data(fresh=True)
        payloads = _sent_payloads(viewer_actor)
        assert payloads, "Expected at least one published frame"
        for dte in payloads:
            assert len(dte.data) == 1

    def test_subtopic_dwa_name_matches_topic(self, viewer_actor):
        """The DWA name inside the payload matches the sub-topic channel name."""
        viewer_actor.query_data(fresh=True)
        for frame_list in viewer_actor.publisher.socket._s:
            topic = frame_list[0].decode() if isinstance(frame_list[0], bytes) else frame_list[0]
            channel = topic.split('/')[-1]
            from serializall import SerializableFactory
            dte = SerializableFactory().get_apply_deserializer(frame_list[2])
            assert dte.data[0].name == channel

    def test_change_to_only_publishes_written_channel(self, caps_actor):
        """change_to('wavelength', 500) must publish only topic/wavelength, not topic/spectrum."""
        before = len(caps_actor.publisher.socket._s)
        caps_actor.change_to('wavelength', 500.0)
        new_frames = caps_actor.publisher.socket._s[before:]
        topics = [f[0].decode() if isinstance(f[0], bytes) else f[0] for f in new_frames]
        assert all('wavelength' in t for t in topics), (
            f"Expected only wavelength topic; got {topics}"
        )
        assert not any('spectrum' in t for t in topics)

    def test_change_to_dict_publishes_only_written_channels(self, caps_actor):
        """Dict form of change_to publishes exactly the keys in the dict."""
        before = len(caps_actor.publisher.socket._s)
        caps_actor.change_to({'wavelength': 500.0})
        new_frames = caps_actor.publisher.socket._s[before:]
        topics = [f[0].decode() if isinstance(f[0], bytes) else f[0] for f in new_frames]
        assert all('wavelength' in t for t in topics)
        assert not any('spectrum' in t for t in topics)

    def test_no_flat_topic_published(self, viewer_actor):
        """The flat '{actor_name}' topic (without sub-channel) is never published."""
        viewer_actor.query_data(fresh=True)
        topics = _sent_topics(viewer_actor)
        assert not any(t == viewer_actor.name for t in topics)
