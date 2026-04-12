"""Tests for ControllerRegistry (Phase CT-1).

All tests are headless — no Qt event loop, no real ControllerThread.
A ``FakeRegistry`` subclass injects a ``FakeThread`` so the registry
logic can be tested independently of threading.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from pymodaq.control_modules.controller_registry import ControllerKey, ControllerRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeThread:
    """Stand-in for ControllerThread — records calls, never touches hardware."""

    def __init__(self):
        self.close_hardware_called = False
        self.parent_qt_thread = None  # no real QThread

    def close_hardware(self):
        self.close_hardware_called = True


class FakeSettings:
    """Stand-in for pymodaq_gui Parameter."""
    pass


class FakeRegistry(ControllerRegistry):
    """Registry that injects FakeThread + FakeSettings instead of real ones."""

    def _make_settings(self, plugin_class, params_state):
        settings = FakeSettings()
        settings.params_state = params_state
        return settings

    def _make_thread(self, plugin_class, settings):
        return FakeThread()


def make_plugin_class(name='DAQ_Move_Mock', params=None):
    """Return a minimal plugin-class stub."""
    return type(name, (), {'params': params or []})


# ---------------------------------------------------------------------------
# ControllerKey tests
# ---------------------------------------------------------------------------

class TestControllerKey:

    def test_equality(self):
        k1 = ControllerKey('DAQ_Move_Mock', 42)
        k2 = ControllerKey('DAQ_Move_Mock', 42)
        assert k1 == k2

    def test_inequality_class(self):
        assert ControllerKey('DAQ_Move_A', 1) != ControllerKey('DAQ_Move_B', 1)

    def test_inequality_id(self):
        assert ControllerKey('DAQ_Move_A', 1) != ControllerKey('DAQ_Move_A', 2)

    def test_hashable_usable_as_dict_key(self):
        d = {}
        k = ControllerKey('DAQ_Move_Mock', 0)
        d[k] = 'value'
        assert d[k] == 'value'

    def test_hashable_equal_keys_same_hash(self):
        k1 = ControllerKey('DAQ_Move_Mock', 7)
        k2 = ControllerKey('DAQ_Move_Mock', 7)
        assert hash(k1) == hash(k2)

    def test_frozen_immutable(self):
        k = ControllerKey('DAQ_Move_Mock', 1)
        with pytest.raises((AttributeError, TypeError)):
            k.plugin_class = 'other'  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ControllerRegistry.acquire tests
# ---------------------------------------------------------------------------

class TestAcquire:

    def setup_method(self):
        self.registry = FakeRegistry()
        self.plugin_cls = make_plugin_class()
        self.key = ControllerKey(self.plugin_cls.__name__, 0)

    def test_first_acquire_returns_thread_and_settings(self):
        thread, settings = self.registry.acquire(self.key, self.plugin_cls)
        assert isinstance(thread, FakeThread)
        assert isinstance(settings, FakeSettings)

    def test_second_acquire_same_key_returns_same_objects(self):
        thread1, settings1 = self.registry.acquire(self.key, self.plugin_cls)
        thread2, settings2 = self.registry.acquire(self.key, self.plugin_cls)
        assert thread1 is thread2
        assert settings1 is settings2

    def test_first_acquire_ref_count_one(self):
        self.registry.acquire(self.key, self.plugin_cls)
        assert self.registry.ref_count(self.key) == 1

    def test_second_acquire_ref_count_two(self):
        self.registry.acquire(self.key, self.plugin_cls)
        self.registry.acquire(self.key, self.plugin_cls)
        assert self.registry.ref_count(self.key) == 2

    def test_different_keys_give_different_threads(self):
        key2 = ControllerKey(self.plugin_cls.__name__, 1)
        thread1, _ = self.registry.acquire(self.key, self.plugin_cls)
        thread2, _ = self.registry.acquire(key2, self.plugin_cls)
        assert thread1 is not thread2

    def test_params_state_passed_to_settings_on_first_acquire(self):
        state = {'key': 'value'}
        _, settings = self.registry.acquire(self.key, self.plugin_cls, params_state=state)
        assert settings.params_state == state

    def test_params_state_ignored_for_guest(self):
        _, settings_first = self.registry.acquire(self.key, self.plugin_cls, params_state={'a': 1})
        _, settings_guest = self.registry.acquire(self.key, self.plugin_cls, params_state={'b': 2})
        # guest gets the same settings object — first caller's state wins
        assert settings_first is settings_guest

    def test_is_known_true_after_acquire(self):
        self.registry.acquire(self.key, self.plugin_cls)
        assert self.registry.is_known(self.key)

    def test_is_known_false_before_acquire(self):
        assert not self.registry.is_known(self.key)


# ---------------------------------------------------------------------------
# ControllerRegistry.release tests
# ---------------------------------------------------------------------------

class TestRelease:

    def setup_method(self):
        self.registry = FakeRegistry()
        self.plugin_cls = make_plugin_class()
        self.key = ControllerKey(self.plugin_cls.__name__, 0)

    def test_release_decrements_ref_count(self):
        self.registry.acquire(self.key, self.plugin_cls)
        self.registry.acquire(self.key, self.plugin_cls)
        self.registry.release(self.key)
        assert self.registry.ref_count(self.key) == 1

    def test_release_to_zero_removes_entry(self):
        self.registry.acquire(self.key, self.plugin_cls)
        self.registry.release(self.key)
        assert not self.registry.is_known(self.key)

    def test_release_to_zero_calls_close_hardware(self):
        thread, _ = self.registry.acquire(self.key, self.plugin_cls)
        self.registry.release(self.key)
        assert thread.close_hardware_called

    def test_release_unknown_key_is_noop(self):
        unknown = ControllerKey('DAQ_Move_Unknown', 99)
        self.registry.release(unknown)  # must not raise

    def test_ref_count_zero_for_unknown_key(self):
        assert self.registry.ref_count(self.key) == 0

    def test_double_release_is_safe(self):
        """Releasing twice after acquiring once should not raise."""
        thread, _ = self.registry.acquire(self.key, self.plugin_cls)
        self.registry.release(self.key)
        self.registry.release(self.key)  # second release: key unknown, noop

    def test_reacquire_after_full_release_creates_new_thread(self):
        thread1, _ = self.registry.acquire(self.key, self.plugin_cls)
        self.registry.release(self.key)
        thread2, _ = self.registry.acquire(self.key, self.plugin_cls)
        assert thread1 is not thread2


# ---------------------------------------------------------------------------
# ControllerRegistry.close_all tests
# ---------------------------------------------------------------------------

class TestCloseAll:

    def setup_method(self):
        self.registry = FakeRegistry()
        self.plugin_cls = make_plugin_class()

    def test_close_all_tears_down_all_threads(self):
        key1 = ControllerKey(self.plugin_cls.__name__, 0)
        key2 = ControllerKey(self.plugin_cls.__name__, 1)
        thread1, _ = self.registry.acquire(key1, self.plugin_cls)
        thread2, _ = self.registry.acquire(key2, self.plugin_cls)
        self.registry.close_all()
        assert thread1.close_hardware_called
        assert thread2.close_hardware_called

    def test_close_all_clears_entries(self):
        key = ControllerKey(self.plugin_cls.__name__, 0)
        self.registry.acquire(key, self.plugin_cls)
        self.registry.close_all()
        assert not self.registry.is_known(key)

    def test_close_all_on_empty_registry_is_noop(self):
        self.registry.close_all()  # must not raise


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

class TestSingleton:

    def setup_method(self):
        # Reset the global singleton before each test.
        ControllerRegistry._reset_global()

    def teardown_method(self):
        # Clean up after each test.
        if ControllerRegistry._global is not None:
            ControllerRegistry._global.close_all()
        ControllerRegistry._reset_global()

    def test_get_returns_same_instance(self):
        r1 = ControllerRegistry.get()
        r2 = ControllerRegistry.get()
        assert r1 is r2

    def test_get_returns_controller_registry_instance(self):
        assert isinstance(ControllerRegistry.get(), ControllerRegistry)

    def test_reset_global_creates_fresh_instance(self):
        r1 = ControllerRegistry.get()
        ControllerRegistry._reset_global()
        r2 = ControllerRegistry.get()
        assert r1 is not r2


# ---------------------------------------------------------------------------
# Thread-safety smoke test
# ---------------------------------------------------------------------------

class TestThreadSafety:
    """Concurrent acquire/release should not corrupt ref-counts."""

    def test_concurrent_acquire_same_key(self):
        registry = FakeRegistry()
        plugin_cls = make_plugin_class()
        key = ControllerKey(plugin_cls.__name__, 0)
        results = []
        errors = []

        def worker():
            try:
                thread, settings = registry.acquire(key, plugin_cls)
                results.append((thread, settings))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 10
        # All callers should get the same thread and settings objects.
        assert all(r[0] is results[0][0] for r in results)
        assert all(r[1] is results[0][1] for r in results)
        assert registry.ref_count(key) == 10

    def test_concurrent_release(self):
        registry = FakeRegistry()
        plugin_cls = make_plugin_class()
        key = ControllerKey(plugin_cls.__name__, 0)

        # Acquire 10 times first.
        for _ in range(10):
            registry.acquire(key, plugin_cls)

        errors = []

        def worker():
            try:
                registry.release(key)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert not registry.is_known(key)
