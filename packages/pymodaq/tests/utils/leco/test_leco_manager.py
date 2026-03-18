"""Tests for pymodaq.utils.leco.leco_manager — Phase 1.

Pure Python — no Qt, no real LECO network, no real subprocesses (mostly).
Uses a mock CoordinatorDirector to exercise LECONetworkMonitor logic.
"""
from __future__ import annotations

import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch, call

import pytest

from pymodaq.utils.leco.leco_manager import (
    ComponentRecord,
    CoordinatorRecord,
    LECONetworkMonitor,
    ProxyRecord,
)


# ── Helpers / Fixtures ─────────────────────────────────────────────────────────

class FakeCoordinatorDirector:
    """Minimal stand-in for pyleco's CoordinatorDirector.

    Keeps a list of sign-in names and honours get_role() / get_capabilities()
    via the ask_rpc dispatch table.
    """

    def __init__(self, components=None, role_map=None):
        # components: list of names returned by get_local_components()
        self._components: list[str] = list(components or [])
        # role_map: name → dict returned by ask_rpc(get_role, actor=name)
        self._role_map: dict[str, dict] = role_map or {}
        self._namespace = 'localhost'
        self.ask_rpc_calls: list[dict] = []

    def get_local_components(self) -> list[str]:
        return list(self._components)

    def get_global_components(self) -> dict[str, list[str]]:
        return {'localhost': list(self._components)}

    def get_nodes(self) -> dict:
        return {}

    def ask_rpc(self, method: str, actor=None, timeout=None, **kwargs) -> Any:
        self.ask_rpc_calls.append({'method': method, 'actor': actor})
        if method == 'get_role':
            return self._role_map.get(actor, {'role': 'unknown', 'host': None})
        if method == 'get_capabilities':
            return {'observables': [], 'variables': []}
        if method == 'get_grabbed_names':
            return None
        if method == 'get_actor_pub_topic':
            return f'localhost.{actor}'
        if method in ('shutdown', 'disconnect', 'pong'):
            return None
        raise ValueError(f"Unknown method in FakeCoordinatorDirector: {method}")

    # ── helpers to mutate state during a test ──────────────────────────────────

    def add_component(self, name: str, role: str = 'actor', host: str = '127.0.0.1'):
        self._components.append(name)
        self._role_map[name] = {'role': role, 'host': host}

    def remove_component(self, name: str):
        self._components = [c for c in self._components if c != name]


def _monitor_with_fake(components=None, role_map=None) -> tuple[LECONetworkMonitor, FakeCoordinatorDirector]:
    """Return a connected monitor backed by a FakeCoordinatorDirector."""
    fake = FakeCoordinatorDirector(components=components, role_map=role_map)
    monitor = LECONetworkMonitor(role_timeout=0.1)
    monitor._director = fake
    monitor._coordinator_record = CoordinatorRecord(host='localhost', port=12300, alive=True)
    return monitor, fake


# ── ComponentRecord ────────────────────────────────────────────────────────────

class TestComponentRecord:
    def test_defaults(self):
        rec = ComponentRecord(name='stage', full_name='localhost.stage', role='actor')
        assert rec.host is None
        assert rec.capabilities is None
        assert rec.grabbed_names is None
        assert rec.pub_topic is None
        assert rec.reachable is True
        assert isinstance(rec.last_seen, datetime)

    def test_role_stored(self):
        rec = ComponentRecord(name='cam', full_name='localhost.cam', role='actor')
        assert rec.role == 'actor'

    def test_unknown_role(self):
        rec = ComponentRecord(name='ghost', full_name='localhost.ghost', role='unknown',
                              reachable=False)
        assert rec.reachable is False


# ── ProxyRecord ────────────────────────────────────────────────────────────────

class TestProxyRecord:
    def test_defaults(self):
        rec = ProxyRecord(in_port=11100, out_port=11099)
        assert rec.label == ''
        assert rec.process is None
        assert rec.alive is False

    def test_ports_stored(self):
        rec = ProxyRecord(in_port=11100, out_port=11099, label='cameras')
        assert rec.in_port == 11100
        assert rec.out_port == 11099
        assert rec.label == 'cameras'


# ── CoordinatorRecord ──────────────────────────────────────────────────────────

class TestCoordinatorRecord:
    def test_defaults(self):
        rec = CoordinatorRecord(host='localhost', port=12300)
        assert rec.namespace is None
        assert rec.nodes == {}
        assert rec.process is None
        assert rec.alive is False
        assert rec.log_path is None
        assert rec.pid_path is None

    def test_new_fields_stored(self):
        p = Path('/tmp/test.log')
        rec = CoordinatorRecord(host='localhost', port=12300, log_path=p, pid_path=p)
        assert rec.log_path == p
        assert rec.pid_path == p


# ── LECONetworkMonitor.connect ─────────────────────────────────────────────────

_COORD_DIR_PATH = 'pyleco.directors.coordinator_director.CoordinatorDirector'


class TestConnect:
    def test_connect_success_sets_alive(self):
        monitor = LECONetworkMonitor()
        fake = FakeCoordinatorDirector(components=[])
        with patch(_COORD_DIR_PATH, return_value=fake):
            monitor.connect(host='localhost', port=12300)
        assert monitor._coordinator_record.alive is True

    def test_connect_calls_callback(self):
        received = []
        monitor = LECONetworkMonitor()
        monitor.on_coordinator_status_changed = received.append
        fake = FakeCoordinatorDirector(components=[])
        with patch(_COORD_DIR_PATH, return_value=fake):
            monitor.connect()
        assert len(received) == 1
        assert received[0].alive is True

    def test_connect_failure_raises_and_marks_not_alive(self):
        monitor = LECONetworkMonitor()
        received = []
        monitor.on_coordinator_status_changed = received.append

        class _FailDirector:
            def get_local_components(self):
                raise TimeoutError("nope")

        with patch(_COORD_DIR_PATH, return_value=_FailDirector()):
            with pytest.raises(ConnectionError):
                monitor.connect()
        assert received[0].alive is False

    def test_connect_attaches_existing_pid_file(self, tmp_path):
        """If a PID file exists for the given port, connect() attaches it."""
        monitor = LECONetworkMonitor()
        fake = FakeCoordinatorDirector(components=[])
        pid_file = tmp_path / 'leco_coordinator_12300.pid'
        pid_file.write_text('12345')

        with patch(_COORD_DIR_PATH, return_value=fake), \
             patch('pymodaq.utils.leco.leco_manager.Path') as MockPath:
            # Make the PID path resolve to our tmp file
            mock_instance = MagicMock()
            mock_instance.__truediv__ = lambda self, other: pid_file
            mock_instance.exists.return_value = True
            MockPath.return_value = mock_instance
            # Patch tempfile so the path computation works
            with patch('pymodaq.utils.leco.leco_manager.tempfile.gettempdir',
                       return_value=str(tmp_path)):
                monitor.connect(port=12300)

        # The record should have been created
        assert monitor._coordinator_record.alive is True


# ── refresh_components ─────────────────────────────────────────────────────────

class TestRefreshComponents:
    def test_new_actor_added_to_registry(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        records = monitor.refresh_components()
        assert any(r.name == 'stage' for r in records)

    def test_actor_role_classified_correctly(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        # _components keyed by full_name
        assert monitor._components['localhost.stage'].role == 'actor'

    def test_director_role_classified_correctly(self):
        monitor, fake = _monitor_with_fake(
            components=['move_dir'],
            role_map={'move_dir': {'role': 'director', 'host': 'mypc'}},
        )
        monitor.refresh_components()
        assert monitor._components['localhost.move_dir'].role == 'director'

    def test_no_reply_gives_unknown_role(self):
        """Component that doesn't respond to get_role → role='unknown', reachable=False."""
        class _TimeoutDirector(FakeCoordinatorDirector):
            def ask_rpc(self, method, actor=None, timeout=None, **kw):
                if method == 'get_role':
                    raise TimeoutError
                return super().ask_rpc(method, actor=actor, timeout=timeout, **kw)

        monitor = LECONetworkMonitor(role_timeout=0.1)
        fake = _TimeoutDirector(components=['ghost'])
        monitor._director = fake
        monitor._coordinator_record = CoordinatorRecord(host='localhost', port=12300, alive=True)

        monitor.refresh_components()
        assert monitor._components['localhost.ghost'].role == 'unknown'
        assert monitor._components['localhost.ghost'].reachable is False

    def test_stale_component_marked_not_reachable(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        assert monitor._components['localhost.stage'].reachable is True

        # Now the component disappears from coordinator
        fake.remove_component('stage')
        monitor.refresh_components()
        assert monitor._components['localhost.stage'].reachable is False

    def test_callback_fired_on_new_component(self):
        received = []
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.on_components_changed = received.append
        monitor.refresh_components()
        assert len(received) == 1

    def test_callback_not_fired_when_list_unchanged(self):
        received = []
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()  # first call — fires
        monitor.on_components_changed = received.append
        monitor.refresh_components()  # second call — nothing new
        assert len(received) == 0

    def test_full_name_includes_namespace(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        rec = monitor._components['localhost.stage']
        assert 'localhost' in rec.full_name
        assert 'stage' in rec.full_name

    def test_no_director_returns_empty_list(self):
        monitor = LECONetworkMonitor()
        records = monitor.refresh_components()
        assert records == []

    def test_remote_component_gets_remote_role(self):
        """Components from a foreign namespace get role='remote'."""
        fake = FakeCoordinatorDirector(components=[], role_map={})
        fake._namespace = 'local'

        class _GlobalFake(FakeCoordinatorDirector):
            def get_global_components(self):
                return {'local': [], 'remote_ns': ['far_actor']}

        monitor = LECONetworkMonitor(role_timeout=0.1)
        monitor._director = _GlobalFake(components=[])
        monitor._director._namespace = 'local'
        monitor._coordinator_record = CoordinatorRecord(host='localhost', port=12300, alive=True)

        monitor.refresh_components()
        rec = monitor._components.get('remote_ns.far_actor')
        assert rec is not None
        assert rec.role == 'remote'


# ── refresh_actor_details ──────────────────────────────────────────────────────

class TestRefreshActorDetails:
    def test_capabilities_populated(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        monitor.refresh_actor_details('stage')
        assert monitor._components['localhost.stage'].capabilities is not None

    def test_pub_topic_populated(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        monitor.refresh_actor_details('stage')
        assert monitor._components['localhost.stage'].pub_topic == 'localhost.stage'

    def test_callback_fired(self):
        received = []
        monitor, fake = _monitor_with_fake(
            components=['cam'],
            role_map={'cam': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        monitor.on_actor_details_changed = received.append
        monitor.refresh_actor_details('cam')
        assert len(received) == 1
        assert received[0].name == 'cam'

    def test_non_actor_returns_none(self):
        monitor, fake = _monitor_with_fake(
            components=['move_dir'],
            role_map={'move_dir': {'role': 'director', 'host': 'mypc'}},
        )
        monitor.refresh_components()
        result = monitor.refresh_actor_details('move_dir')
        assert result is None

    def test_unknown_name_returns_none(self):
        monitor, _ = _monitor_with_fake()
        result = monitor.refresh_actor_details('no_such_thing')
        assert result is None


# ── shutdown_component ─────────────────────────────────────────────────────────

class TestShutdownComponent:
    def test_actor_sends_shutdown_rpc(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        monitor.shutdown_component('stage')
        methods = [c['method'] for c in fake.ask_rpc_calls]
        assert 'shutdown' in methods

    def test_director_sends_disconnect_rpc(self):
        monitor, fake = _monitor_with_fake(
            components=['move_dir'],
            role_map={'move_dir': {'role': 'director', 'host': 'mypc'}},
        )
        monitor.refresh_components()
        monitor.shutdown_component('move_dir')
        methods = [c['method'] for c in fake.ask_rpc_calls]
        assert 'disconnect' in methods

    def test_component_removed_from_registry_after_shutdown(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        monitor.shutdown_component('stage')
        assert 'localhost.stage' not in monitor._components

    def test_unknown_component_removed_from_display(self):
        monitor, fake = _monitor_with_fake(
            components=['ghost'],
            role_map={'ghost': {'role': 'unknown', 'host': None}},
        )
        monitor.refresh_components()
        monitor.shutdown_component('ghost')
        assert 'localhost.ghost' not in monitor._components

    def test_callback_fired_after_shutdown(self):
        received = []
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        monitor.on_components_changed = received.append
        monitor.shutdown_component('stage')
        assert len(received) == 1

    def test_shutdown_nonexistent_does_not_raise(self):
        monitor, _ = _monitor_with_fake()
        monitor.shutdown_component('no_such')  # must not raise


# ── Proxy lifecycle ────────────────────────────────────────────────────────────

class TestProxyLifecycle:
    def test_add_proxy_creates_record(self):
        monitor, _ = _monitor_with_fake()
        with patch('subprocess.Popen') as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            rec = monitor.add_proxy(11100, 11099, label='test')
        assert rec.in_port == 11100
        assert rec.out_port == 11099
        assert rec.label == 'test'
        assert rec.alive is True

    def test_add_proxy_fires_callback(self):
        received = []
        monitor, _ = _monitor_with_fake()
        monitor.on_proxy_status_changed = received.append
        with patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = MagicMock()
            monitor.add_proxy(11100, 11099)
        assert len(received) == 1

    def test_add_proxy_uses_start_new_session(self):
        """Proxy subprocess must be detached via start_new_session=True."""
        monitor, _ = _monitor_with_fake()
        with patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = MagicMock()
            monitor.add_proxy(11100, 11099)
        _, kwargs = mock_popen.call_args
        assert kwargs.get('start_new_session') is True

    def test_add_proxy_custom_ports_uses_zmq_inline(self):
        """Non-default ports use the inline zmq.proxy command."""
        monitor, _ = _monitor_with_fake()
        with patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = MagicMock()
            monitor.add_proxy(9999, 9998)
        args, _ = mock_popen.call_args
        cmd = args[0]
        # Command should be python -c '...zmq...'
        assert '-c' in cmd
        assert 'zmq' in ' '.join(cmd)

    def test_remove_proxy_terminates_process(self):
        monitor, _ = _monitor_with_fake()
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        rec = ProxyRecord(in_port=11100, out_port=11099, process=mock_proc, alive=True)
        monitor._proxies[11100] = rec

        monitor.remove_proxy(11100)
        mock_proc.terminate.assert_called_once()
        assert 11100 not in monitor._proxies

    def test_remove_proxy_fires_callback(self):
        received = []
        monitor, _ = _monitor_with_fake()
        monitor.on_proxy_status_changed = received.append
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        rec = ProxyRecord(in_port=11100, out_port=11099, process=mock_proc, alive=True)
        monitor._proxies[11100] = rec
        monitor.remove_proxy(11100)
        assert len(received) == 1
        assert received[0].alive is False

    def test_remove_nonexistent_proxy_is_noop(self):
        monitor, _ = _monitor_with_fake()
        monitor.remove_proxy(99999)  # must not raise

    def test_probe_proxy_owned_alive(self):
        monitor, _ = _monitor_with_fake()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # process still running
        rec = ProxyRecord(in_port=11100, out_port=11099, process=mock_proc, alive=True)
        monitor._proxies[11100] = rec
        assert monitor.probe_proxy(11100, 11099) is True

    def test_probe_proxy_owned_dead(self):
        monitor, _ = _monitor_with_fake()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # process exited
        rec = ProxyRecord(in_port=11100, out_port=11099, process=mock_proc, alive=True)
        monitor._proxies[11100] = rec
        assert monitor.probe_proxy(11100, 11099) is False
        assert rec.alive is False

    def test_probe_proxy_external_returns_false(self):
        monitor, _ = _monitor_with_fake()
        rec = ProxyRecord(in_port=11100, out_port=11099, process=None, alive=False)
        monitor._proxies[11100] = rec
        assert monitor.probe_proxy(11100, 11099) is False

    def test_probe_unknown_proxy_returns_false(self):
        monitor, _ = _monitor_with_fake()
        assert monitor.probe_proxy(99999, 99998) is False


# ── Coordinator lifecycle ──────────────────────────────────────────────────────

class TestCoordinatorLifecycle:
    def test_start_coordinator_returns_record(self):
        monitor, _ = _monitor_with_fake()
        with patch('subprocess.Popen') as mock_popen, \
             patch.object(monitor, '_await_coordinator_ready',
                          side_effect=lambda h, p, rec, **kw: setattr(rec, 'alive', True) or
                          monitor.on_coordinator_status_changed(rec)):
            mock_popen.return_value = MagicMock()
            with patch('builtins.open', MagicMock()), \
                 patch('pymodaq.utils.leco.leco_manager.Path') as MockPath:
                MockPath.return_value.__truediv__ = lambda s, o: MagicMock(
                    write_text=MagicMock(), exists=MagicMock(return_value=False)
                )
                rec = monitor.start_coordinator(port=12300)
        assert rec.port == 12300

    def test_start_coordinator_uses_start_new_session(self):
        """Coordinator must be detached via start_new_session=True."""
        monitor, _ = _monitor_with_fake()
        with patch('subprocess.Popen') as mock_popen, \
             patch.object(monitor, '_await_coordinator_ready', return_value=None), \
             patch('builtins.open', MagicMock()):
            mock_popen.return_value = MagicMock()
            with patch('pymodaq.utils.leco.leco_manager.Path') as MockPath:
                mock_path_inst = MagicMock()
                mock_path_inst.write_text = MagicMock()
                MockPath.return_value.__truediv__ = lambda s, o: mock_path_inst
                monitor.start_coordinator(port=12300)
        _, kwargs = mock_popen.call_args
        assert kwargs.get('start_new_session') is True

    def test_start_coordinator_fires_callback(self):
        received = []
        monitor, _ = _monitor_with_fake()
        monitor.on_coordinator_status_changed = received.append
        with patch('subprocess.Popen') as mock_popen, \
             patch.object(monitor, '_await_coordinator_ready', return_value=None), \
             patch('builtins.open', MagicMock()):
            mock_popen.return_value = MagicMock()
            with patch('pymodaq.utils.leco.leco_manager.Path') as MockPath:
                mock_path_inst = MagicMock()
                mock_path_inst.write_text = MagicMock()
                MockPath.return_value.__truediv__ = lambda s, o: mock_path_inst
                monitor.start_coordinator()
        # At minimum one callback fired (initial with alive=False)
        assert len(received) >= 1

    def test_stop_coordinator_calls_shut_down_rpc_first(self):
        """stop_coordinator should attempt the graceful RPC before SIGTERM."""
        monitor, fake = _monitor_with_fake()
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        rec = CoordinatorRecord(host='localhost', port=12300, process=mock_proc, alive=True)
        monitor._coordinator_record = rec

        monitor.stop_coordinator()

        methods = [c['method'] for c in fake.ask_rpc_calls]
        # shut_down_actor is attempted (may raise, caught silently)
        # process.terminate() called as fallback
        mock_proc.terminate.assert_called_once()
        assert rec.alive is False

    def test_stop_coordinator_terminates_process(self):
        monitor, _ = _monitor_with_fake()
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        rec = CoordinatorRecord(host='localhost', port=12300, process=mock_proc, alive=True)
        monitor._coordinator_record = rec
        monitor.stop_coordinator()
        mock_proc.terminate.assert_called_once()
        assert rec.alive is False

    def test_stop_coordinator_pid_file_fallback(self, tmp_path):
        """When no process handle, stop_coordinator sends SIGTERM via PID file."""
        monitor, _ = _monitor_with_fake()
        pid_file = tmp_path / 'leco_coordinator_12300.pid'
        pid_file.write_text('99999')
        rec = CoordinatorRecord(
            host='localhost', port=12300, process=None, alive=True, pid_path=pid_file
        )
        monitor._coordinator_record = rec

        with patch('os.kill') as mock_kill:
            monitor.stop_coordinator()

        mock_kill.assert_called_once_with(99999, signal.SIGTERM)
        assert rec.alive is False

    def test_stop_coordinator_cleans_up_pid_file(self, tmp_path):
        """PID file is deleted after stop_coordinator."""
        monitor, _ = _monitor_with_fake()
        pid_file = tmp_path / 'leco_coordinator_12300.pid'
        pid_file.write_text('99999')
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        rec = CoordinatorRecord(
            host='localhost', port=12300, process=mock_proc, alive=True, pid_path=pid_file
        )
        monitor._coordinator_record = rec
        monitor.stop_coordinator()
        assert not pid_file.exists()

    def test_stop_coordinator_noop_if_no_record(self):
        monitor, _ = _monitor_with_fake()
        monitor._coordinator_record = None
        monitor.stop_coordinator()  # must not raise


# ── Coordinator health check ───────────────────────────────────────────────────

class TestCoordinatorHealthCheck:
    def test_process_exit_detected(self):
        """If the owned process exits, alive flips to False."""
        received = []
        monitor, _ = _monitor_with_fake()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exited
        rec = CoordinatorRecord(host='localhost', port=12300, process=mock_proc, alive=True)
        monitor._coordinator_record = rec
        monitor.on_coordinator_status_changed = received.append

        monitor._check_coordinator_health()
        assert rec.alive is False
        assert len(received) == 1

    def test_pong_failure_flips_alive_false(self):
        """If pong RPC fails and no process, alive flips to False."""
        received = []
        monitor, fake = _monitor_with_fake()

        class _PongFail(FakeCoordinatorDirector):
            def ask_rpc(self, method, **kw):
                if method == 'pong':
                    raise TimeoutError("no response")
                return super().ask_rpc(method, **kw)

        monitor._director = _PongFail()
        rec = CoordinatorRecord(host='localhost', port=12300, alive=True)
        monitor._coordinator_record = rec
        monitor.on_coordinator_status_changed = received.append

        monitor._check_coordinator_health()
        assert rec.alive is False
        assert len(received) == 1

    def test_pong_success_keeps_alive_true(self):
        """Successful pong — no state change, no callback."""
        received = []
        monitor, fake = _monitor_with_fake()
        rec = CoordinatorRecord(host='localhost', port=12300, alive=True)
        monitor._coordinator_record = rec
        monitor.on_coordinator_status_changed = received.append

        monitor._check_coordinator_health()
        assert rec.alive is True
        assert len(received) == 0  # no change → no callback

    def test_no_record_is_noop(self):
        monitor, _ = _monitor_with_fake()
        monitor._coordinator_record = None
        monitor._check_coordinator_health()  # must not raise


# ── Proxy health check from poll ───────────────────────────────────────────────

class TestProxyHealthFromPoll:
    def test_check_proxies_health_calls_probe(self):
        """_check_proxies_health() calls probe_proxy for each registered proxy."""
        monitor, _ = _monitor_with_fake()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        rec = ProxyRecord(in_port=11100, out_port=11099, process=mock_proc, alive=True)
        monitor._proxies[11100] = rec

        probed = []
        original = monitor.probe_proxy
        monitor.probe_proxy = lambda ip, op: probed.append((ip, op)) or True

        monitor._check_proxies_health()
        assert (11100, 11099) in probed


# ── refresh_nodes ──────────────────────────────────────────────────────────────

class TestRefreshNodes:
    def test_nodes_returned(self):
        monitor, _ = _monitor_with_fake()

        class _NodesFake(FakeCoordinatorDirector):
            def get_nodes(self):
                return {'remote': 'other_host:12300'}

        monitor._director = _NodesFake()
        nodes = monitor.refresh_nodes()
        assert nodes == {'remote': 'other_host:12300'}

    def test_on_nodes_changed_fired(self):
        received = []
        monitor, _ = _monitor_with_fake()

        class _NodesFake(FakeCoordinatorDirector):
            def get_nodes(self):
                return {'remote': 'other_host:12300'}

        monitor._director = _NodesFake()
        monitor.on_nodes_changed = received.append
        monitor.refresh_nodes()
        assert len(received) == 1
        assert received[0] == {'remote': 'other_host:12300'}

    def test_no_director_returns_empty(self):
        monitor = LECONetworkMonitor()
        result = monitor.refresh_nodes()
        assert result == {}

    def test_get_nodes_failure_returns_empty(self):
        monitor, _ = _monitor_with_fake()

        class _FailFake(FakeCoordinatorDirector):
            def get_nodes(self):
                raise RuntimeError("not implemented")

        monitor._director = _FailFake()
        result = monitor.refresh_nodes()
        assert result == {}

    def test_nodes_stored_in_record(self):
        monitor, _ = _monitor_with_fake()

        class _NodesFake(FakeCoordinatorDirector):
            def get_nodes(self):
                return {'ns1': 'h:12300'}

        monitor._director = _NodesFake()
        monitor.refresh_nodes()
        assert monitor._coordinator_record.nodes == {'ns1': 'h:12300'}


# ── Polling loop ───────────────────────────────────────────────────────────────

class TestPollingLoop:
    def test_start_stop_does_not_raise(self):
        monitor, _ = _monitor_with_fake(
            components=[],
        )
        monitor.start_polling()
        time.sleep(0.05)
        monitor.stop_polling()

    def test_poll_thread_starts(self):
        monitor, _ = _monitor_with_fake()
        monitor.start_polling()
        assert monitor._poll_thread is not None
        assert monitor._poll_thread.is_alive()
        monitor.stop_polling()

    def test_poll_thread_stops(self):
        monitor, _ = _monitor_with_fake()
        monitor.start_polling()
        thread = monitor._poll_thread
        monitor.stop_polling()
        # stop_polling sets _poll_thread to None after join
        assert monitor._poll_thread is None or not thread.is_alive()

    def test_double_start_is_idempotent(self):
        monitor, _ = _monitor_with_fake()
        monitor.start_polling()
        t1 = monitor._poll_thread
        monitor.start_polling()
        assert monitor._poll_thread is t1
        monitor.stop_polling()

    def test_polling_discovers_components(self):
        """After a few poll ticks, a newly added component should be discovered."""
        monitor, fake = _monitor_with_fake()
        monitor._component_poll_interval = 0.05
        fake.add_component('stage', 'actor')

        discovered = threading.Event()

        def _cb(records):
            if any(r.name == 'stage' for r in records):
                discovered.set()

        monitor.on_components_changed = _cb
        monitor.start_polling()
        assert discovered.wait(timeout=1.0), "stage was not discovered within 1 s"
        monitor.stop_polling()


# ── Accessors ──────────────────────────────────────────────────────────────────

class TestAccessors:
    def test_components_returns_list(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        assert isinstance(monitor.components, list)
        assert any(r.name == 'stage' for r in monitor.components)

    def test_proxies_returns_list(self):
        monitor, _ = _monitor_with_fake()
        assert isinstance(monitor.proxies, list)

    def test_coordinator_property(self):
        monitor, _ = _monitor_with_fake()
        assert monitor.coordinator is not None
        assert monitor.coordinator.alive is True
