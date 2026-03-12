"""Tests for pymodaq.utils.leco.leco_manager — Phase 1.

Pure Python — no Qt, no real LECO network, no real subprocesses (mostly).
Uses a mock CoordinatorDirector to exercise LECONetworkMonitor logic.
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
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
        if method in ('shutdown', 'disconnect'):
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
        assert monitor._components['stage'].role == 'actor'

    def test_director_role_classified_correctly(self):
        monitor, fake = _monitor_with_fake(
            components=['move_dir'],
            role_map={'move_dir': {'role': 'director', 'host': 'mypc'}},
        )
        monitor.refresh_components()
        assert monitor._components['move_dir'].role == 'director'

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
        assert monitor._components['ghost'].role == 'unknown'
        assert monitor._components['ghost'].reachable is False

    def test_stale_component_marked_not_reachable(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        assert monitor._components['stage'].reachable is True

        # Now the component disappears from coordinator
        fake.remove_component('stage')
        monitor.refresh_components()
        assert monitor._components['stage'].reachable is False

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
        rec = monitor._components['stage']
        assert 'localhost' in rec.full_name
        assert 'stage' in rec.full_name

    def test_no_director_returns_empty_list(self):
        monitor = LECONetworkMonitor()
        records = monitor.refresh_components()
        assert records == []


# ── refresh_actor_details ──────────────────────────────────────────────────────

class TestRefreshActorDetails:
    def test_capabilities_populated(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        monitor.refresh_actor_details('stage')
        assert monitor._components['stage'].capabilities is not None

    def test_pub_topic_populated(self):
        monitor, fake = _monitor_with_fake(
            components=['stage'],
            role_map={'stage': {'role': 'actor', 'host': '127.0.0.1'}},
        )
        monitor.refresh_components()
        monitor.refresh_actor_details('stage')
        assert monitor._components['stage'].pub_topic == 'localhost.stage'

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
        assert 'stage' not in monitor._components

    def test_unknown_component_removed_from_display(self):
        monitor, fake = _monitor_with_fake(
            components=['ghost'],
            role_map={'ghost': {'role': 'unknown', 'host': None}},
        )
        monitor.refresh_components()
        monitor.shutdown_component('ghost')
        assert 'ghost' not in monitor._components

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
        with patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = MagicMock()
            rec = monitor.start_coordinator(port=12300)
        assert rec.alive is True
        assert rec.port == 12300

    def test_start_coordinator_fires_callback(self):
        received = []
        monitor, _ = _monitor_with_fake()
        monitor.on_coordinator_status_changed = received.append
        with patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = MagicMock()
            monitor.start_coordinator()
        assert len(received) == 1
        assert received[0].alive is True

    def test_stop_coordinator_terminates_process(self):
        monitor, _ = _monitor_with_fake()
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        rec = CoordinatorRecord(host='localhost', port=12300, process=mock_proc, alive=True)
        monitor._coordinator_record = rec
        monitor.stop_coordinator()
        mock_proc.terminate.assert_called_once()
        assert rec.alive is False

    def test_stop_coordinator_noop_if_no_process(self):
        monitor, _ = _monitor_with_fake()
        monitor._coordinator_record = CoordinatorRecord(host='localhost', port=12300)
        monitor.stop_coordinator()  # must not raise

    def test_stop_coordinator_noop_if_no_record(self):
        monitor, _ = _monitor_with_fake()
        monitor._coordinator_record = None
        monitor.stop_coordinator()  # must not raise


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
