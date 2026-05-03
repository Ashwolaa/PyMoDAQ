"""Tests for ControllerRegistry (Phase CT-1).

All tests are headless — no Qt event loop, no real ControllerThread.
A ``FakeRegistry`` subclass injects a ``FakeThread`` so the registry
logic can be tested independently of threading.

Key concept
-----------
``ControllerKey`` is keyed on ``hardware_class`` (the shared SDK driver),
not on the plugin wrapper class.  Two plugin classes that declare the same
``hardware_class`` resolve to the same key and therefore share one thread:

    class DAQ_Move_MyStage(DAQ_Move_base):
        hardware_class = MyStageDriver   # ← declares shared driver

    class DAQ_0DViewer_MyStage(DAQ_Viewer_base):
        hardware_class = MyStageDriver   # ← same driver → same key → same thread

Plugins that do not declare ``hardware_class`` fall back to ``type(plugin)``,
so existing single-role plugins need no changes.
"""
from __future__ import annotations

import threading

import pytest

from pymodaq.control_modules.controller_registry import ControllerKey, ControllerRegistry, strip_params


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

    def _make_settings(self, plugin_class, params_state, exclude_params=frozenset()):
        settings = FakeSettings()
        settings.params_state = params_state
        return settings

    def _make_thread(self, plugin_class, settings):
        return FakeThread()


def make_hardware_class(name='MyDriver'):
    """Return a minimal SDK driver class stub (the shared hardware_class)."""
    return type(name, (), {})


def make_plugin_class(name='DAQ_Move_Mock', hardware_class=None, params=None):
    """Return a minimal plugin-class stub.

    If *hardware_class* is provided it is set as a class attribute, simulating
    a plugin that declares which physical driver it shares with other plugins.
    If omitted, no ``hardware_class`` attribute is present — the registry falls
    back to using the plugin class itself as the key.
    """
    attrs = {'params': params or []}
    if hardware_class is not None:
        attrs['hardware_class'] = hardware_class
    return type(name, (), attrs)


def key_for(plugin_cls, controller_id=0) -> ControllerKey:
    """Replicate the call-site key derivation used in production code."""
    hw_cls = getattr(plugin_cls, 'hardware_class', plugin_cls)
    return ControllerKey(hardware_class=hw_cls, controller_id=controller_id)


# ---------------------------------------------------------------------------
# ControllerKey tests
# ---------------------------------------------------------------------------

class TestControllerKey:

    def test_equality_same_hardware_class_same_id(self):
        hw = make_hardware_class()
        k1 = ControllerKey(hardware_class=hw, controller_id=42)
        k2 = ControllerKey(hardware_class=hw, controller_id=42)
        assert k1 == k2

    def test_inequality_different_hardware_class(self):
        hw_a = make_hardware_class('DriverA')
        hw_b = make_hardware_class('DriverB')
        assert ControllerKey(hardware_class=hw_a, controller_id=1) != \
               ControllerKey(hardware_class=hw_b, controller_id=1)

    def test_inequality_different_controller_id(self):
        hw = make_hardware_class()
        assert ControllerKey(hardware_class=hw, controller_id=1) != \
               ControllerKey(hardware_class=hw, controller_id=2)

    def test_two_classes_same_name_are_different_hardware_classes(self):
        """Class identity beats name: two distinct classes with the same
        __name__ produce different keys (no aliasing by name)."""
        hw_a = make_hardware_class('MyDriver')
        hw_b = make_hardware_class('MyDriver')
        assert ControllerKey(hardware_class=hw_a, controller_id=0) != \
               ControllerKey(hardware_class=hw_b, controller_id=0)

    def test_hashable_usable_as_dict_key(self):
        hw = make_hardware_class()
        k = ControllerKey(hardware_class=hw, controller_id=0)
        d = {k: 'value'}
        assert d[k] == 'value'

    def test_hashable_equal_keys_same_hash(self):
        hw = make_hardware_class()
        k1 = ControllerKey(hardware_class=hw, controller_id=7)
        k2 = ControllerKey(hardware_class=hw, controller_id=7)
        assert hash(k1) == hash(k2)

    def test_frozen_immutable(self):
        hw = make_hardware_class()
        k = ControllerKey(hardware_class=hw, controller_id=1)
        with pytest.raises((AttributeError, TypeError)):
            k.hardware_class = object  # type: ignore[misc]


# ---------------------------------------------------------------------------
# hardware_class sharing: two plugin classes → one thread
# ---------------------------------------------------------------------------

class TestHardwareClassSharing:
    """Verify that the registry correctly collapses plugin classes that share
    the same physical driver (hardware_class) into a single ControllerThread."""

    def setup_method(self):
        self.registry = FakeRegistry()
        self.driver = make_hardware_class('MyStageDriver')

    def test_two_plugin_classes_same_hardware_class_same_key(self):
        move_cls = make_plugin_class('DAQ_Move_MyStage', hardware_class=self.driver)
        view_cls = make_plugin_class('DAQ_0DViewer_MyStage', hardware_class=self.driver)
        assert key_for(move_cls) == key_for(view_cls)

    def test_two_plugin_classes_same_hardware_class_share_thread(self):
        move_cls = make_plugin_class('DAQ_Move_MyStage', hardware_class=self.driver)
        view_cls = make_plugin_class('DAQ_0DViewer_MyStage', hardware_class=self.driver)
        key = key_for(move_cls)
        thread_move, _ = self.registry.attach(key, move_cls)
        thread_view, _ = self.registry.attach(key, view_cls)
        assert thread_move is thread_view

    def test_two_plugin_classes_same_hardware_class_ref_count_two(self):
        move_cls = make_plugin_class('DAQ_Move_MyStage', hardware_class=self.driver)
        view_cls = make_plugin_class('DAQ_0DViewer_MyStage', hardware_class=self.driver)
        key = key_for(move_cls)
        self.registry.attach(key, move_cls)
        self.registry.attach(key, view_cls)
        assert self.registry.ref_count(key) == 2

    def test_plugin_without_hardware_class_uses_plugin_class_as_key(self):
        """Fallback: plugin not declaring hardware_class keys on itself."""
        cls_a = make_plugin_class('DAQ_Move_Solo')   # no hardware_class
        cls_b = make_plugin_class('DAQ_Move_Solo')   # different object, same name
        # Each plugin class is its own key — no sharing
        assert key_for(cls_a) != key_for(cls_b)

    def test_different_hardware_classes_give_different_threads(self):
        driver_b = make_hardware_class('OtherDriver')
        cls_a = make_plugin_class('DAQ_Move_A', hardware_class=self.driver)
        cls_b = make_plugin_class('DAQ_Move_B', hardware_class=driver_b)
        thread_a, _ = self.registry.attach(key_for(cls_a), cls_a)
        thread_b, _ = self.registry.attach(key_for(cls_b), cls_b)
        assert thread_a is not thread_b

    def test_same_hardware_class_different_controller_id_gives_different_threads(self):
        """controller_id distinguishes two physical units of the same model."""
        cls = make_plugin_class('DAQ_Move_MyStage', hardware_class=self.driver)
        key0 = ControllerKey(hardware_class=self.driver, controller_id=0)
        key1 = ControllerKey(hardware_class=self.driver, controller_id=1)
        thread0, _ = self.registry.attach(key0, cls)
        thread1, _ = self.registry.attach(key1, cls)
        assert thread0 is not thread1


# ---------------------------------------------------------------------------
# X-1: Cross-type sharing (Move + Viewer on same ControllerKey)
# ---------------------------------------------------------------------------

class TestCrossTypeSharing:
    """Move and Viewer that share hardware_class share the CT but get separate hw_settings."""

    def setup_method(self):
        self.registry = FakeRegistry()
        self.driver = make_hardware_class('SharedDriver')
        self.move_cls = make_plugin_class('DAQ_Move_Shared', hardware_class=self.driver)
        self.view_cls = make_plugin_class('DAQ_0DViewer_Shared', hardware_class=self.driver)
        self.key = key_for(self.move_cls)

    def test_same_key(self):
        assert key_for(self.move_cls) == key_for(self.view_cls)

    def test_share_thread(self):
        thread_m, _ = self.registry.attach(self.key, self.move_cls)
        thread_v, _ = self.registry.attach(self.key, self.view_cls)
        assert thread_m is thread_v

    def test_different_hw_settings(self):
        _, hw_m = self.registry.attach(self.key, self.move_cls)
        _, hw_v = self.registry.attach(self.key, self.view_cls)
        assert hw_m is not hw_v

    def test_same_plugin_class_same_hw_settings(self):
        """Two DAQ_Move on the same key must share one hw_settings object."""
        _, hw1 = self.registry.attach(self.key, self.move_cls)
        _, hw2 = self.registry.attach(self.key, self.move_cls)
        assert hw1 is hw2

    def test_ref_count_three_after_move_move_viewer(self):
        self.registry.attach(self.key, self.move_cls)
        self.registry.attach(self.key, self.move_cls)
        self.registry.attach(self.key, self.view_cls)
        assert self.registry.ref_count(self.key) == 3

    def test_second_plugin_type_gets_its_own_params_state(self):
        """params_state passed by the second plugin type is used to build ITS settings."""
        _, hw_m = self.registry.attach(self.key, self.move_cls, params_state={'move': True})
        _, hw_v = self.registry.attach(self.key, self.view_cls, params_state={'view': True})
        # FakeRegistry stores params_state on the FakeSettings object
        assert hw_v.params_state == {'view': True}

    def test_second_plugin_same_class_ignores_new_params_state(self):
        """A second subscriber with the same plugin class must NOT rebuild settings."""
        _, hw1 = self.registry.attach(self.key, self.move_cls, params_state={'first': True})
        _, hw2 = self.registry.attach(self.key, self.move_cls, params_state={'second': True})
        # Same object — params_state from second call was not applied
        assert hw1 is hw2
        assert hw1.params_state == {'first': True}

    def test_teardown_clears_all_plugin_type_entries(self):
        self.registry.attach(self.key, self.move_cls)
        self.registry.attach(self.key, self.view_cls)
        self.registry.detach(self.key)
        self.registry.detach(self.key)
        assert not self.registry.is_known(self.key)


# ---------------------------------------------------------------------------
# ControllerRegistry.attach tests
# ---------------------------------------------------------------------------

class TestAcquire:

    def setup_method(self):
        self.registry = FakeRegistry()
        self.plugin_cls = make_plugin_class()
        self.key = key_for(self.plugin_cls)

    def test_first_acquire_returns_thread_and_settings(self):
        thread, settings = self.registry.attach(self.key, self.plugin_cls)
        assert isinstance(thread, FakeThread)
        assert isinstance(settings, FakeSettings)

    def test_second_acquire_same_key_returns_same_objects(self):
        thread1, settings1 = self.registry.attach(self.key, self.plugin_cls)
        thread2, settings2 = self.registry.attach(self.key, self.plugin_cls)
        assert thread1 is thread2
        assert settings1 is settings2

    def test_first_acquire_ref_count_one(self):
        self.registry.attach(self.key, self.plugin_cls)
        assert self.registry.ref_count(self.key) == 1

    def test_second_acquire_ref_count_two(self):
        self.registry.attach(self.key, self.plugin_cls)
        self.registry.attach(self.key, self.plugin_cls)
        assert self.registry.ref_count(self.key) == 2

    def test_different_controller_id_gives_different_threads(self):
        key2 = ControllerKey(hardware_class=self.plugin_cls, controller_id=1)
        thread1, _ = self.registry.attach(self.key, self.plugin_cls)
        thread2, _ = self.registry.attach(key2, self.plugin_cls)
        assert thread1 is not thread2

    def test_params_state_passed_to_settings_on_first_acquire(self):
        state = {'key': 'value'}
        _, settings = self.registry.attach(self.key, self.plugin_cls, params_state=state)
        assert settings.params_state == state

    def test_params_state_ignored_for_guest(self):
        _, settings_first = self.registry.attach(self.key, self.plugin_cls, params_state={'a': 1})
        _, settings_guest = self.registry.attach(self.key, self.plugin_cls, params_state={'b': 2})
        # guest gets the same settings object — first caller's state wins
        assert settings_first is settings_guest

    def test_is_known_true_after_acquire(self):
        self.registry.attach(self.key, self.plugin_cls)
        assert self.registry.is_known(self.key)

    def test_is_known_false_before_acquire(self):
        assert not self.registry.is_known(self.key)

    def test_subscriber_recorded_on_first_acquire(self):
        sub = object()
        self.registry.attach(self.key, self.plugin_cls, subscriber=sub)
        assert id(sub) in self.registry.subscribers(self.key)

    def test_subscriber_recorded_on_guest_acquire(self):
        sub1, sub2 = object(), object()
        self.registry.attach(self.key, self.plugin_cls, subscriber=sub1)
        self.registry.attach(self.key, self.plugin_cls, subscriber=sub2)
        subs = self.registry.subscribers(self.key)
        assert id(sub1) in subs
        assert id(sub2) in subs

    def test_no_subscriber_acquire_still_works(self):
        self.registry.attach(self.key, self.plugin_cls)
        assert self.registry.subscribers(self.key) == {}

    def test_subscribers_empty_for_unknown_key(self):
        assert self.registry.subscribers(self.key) == {}


# ---------------------------------------------------------------------------
# ControllerRegistry.detach tests
# ---------------------------------------------------------------------------

class TestRelease:

    def setup_method(self):
        self.registry = FakeRegistry()
        self.plugin_cls = make_plugin_class()
        self.key = key_for(self.plugin_cls)

    def test_release_decrements_ref_count(self):
        self.registry.attach(self.key, self.plugin_cls)
        self.registry.attach(self.key, self.plugin_cls)
        self.registry.detach(self.key)
        assert self.registry.ref_count(self.key) == 1

    def test_release_to_zero_removes_entry(self):
        self.registry.attach(self.key, self.plugin_cls)
        self.registry.detach(self.key)
        assert not self.registry.is_known(self.key)

    def test_release_to_zero_calls_close_hardware(self):
        thread, _ = self.registry.attach(self.key, self.plugin_cls)
        self.registry.detach(self.key)
        assert thread.close_hardware_called

    def test_release_unknown_key_is_noop(self):
        unknown_hw = make_hardware_class('UnknownDriver')
        unknown = ControllerKey(hardware_class=unknown_hw, controller_id=99)
        self.registry.detach(unknown)  # must not raise

    def test_ref_count_zero_for_unknown_key(self):
        assert self.registry.ref_count(self.key) == 0

    def test_release_removes_subscriber(self):
        sub = object()
        self.registry.attach(self.key, self.plugin_cls, subscriber=sub)
        self.registry.detach(self.key, subscriber=sub)
        # entry gone (ref_count → 0), so subscribers() returns {}
        assert self.registry.subscribers(self.key) == {}

    def test_release_removes_only_named_subscriber(self):
        sub1, sub2 = object(), object()
        self.registry.attach(self.key, self.plugin_cls, subscriber=sub1)
        self.registry.attach(self.key, self.plugin_cls, subscriber=sub2)
        self.registry.detach(self.key, subscriber=sub1)
        subs = self.registry.subscribers(self.key)
        assert id(sub1) not in subs
        assert id(sub2) in subs

    def test_double_release_is_safe(self):
        """Releasing twice after acquiring once should not raise."""
        self.registry.attach(self.key, self.plugin_cls)
        self.registry.detach(self.key)
        self.registry.detach(self.key)  # second release: key unknown, noop

    def test_reacquire_after_full_release_creates_new_thread(self):
        thread1, _ = self.registry.attach(self.key, self.plugin_cls)
        self.registry.detach(self.key)
        thread2, _ = self.registry.attach(self.key, self.plugin_cls)
        assert thread1 is not thread2


# ---------------------------------------------------------------------------
# ControllerRegistry.close_all tests
# ---------------------------------------------------------------------------

class TestCloseAll:

    def setup_method(self):
        self.registry = FakeRegistry()
        self.plugin_cls = make_plugin_class()

    def test_close_all_tears_down_all_threads(self):
        key1 = ControllerKey(hardware_class=self.plugin_cls, controller_id=0)
        key2 = ControllerKey(hardware_class=self.plugin_cls, controller_id=1)
        thread1, _ = self.registry.attach(key1, self.plugin_cls)
        thread2, _ = self.registry.attach(key2, self.plugin_cls)
        self.registry.close_all()
        assert thread1.close_hardware_called
        assert thread2.close_hardware_called

    def test_close_all_clears_entries(self):
        key = ControllerKey(hardware_class=self.plugin_cls, controller_id=0)
        self.registry.attach(key, self.plugin_cls)
        self.registry.close_all()
        assert not self.registry.is_known(key)

    def test_close_all_on_empty_registry_is_noop(self):
        self.registry.close_all()  # must not raise


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

class TestSingleton:

    def setup_method(self):
        ControllerRegistry._reset_global()

    def teardown_method(self):
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
        key = key_for(plugin_cls)
        results = []
        errors = []

        def worker():
            try:
                thread, settings = registry.attach(key, plugin_cls)
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
        key = key_for(plugin_cls)

        for _ in range(10):
            registry.attach(key, plugin_cls)

        errors = []

        def worker():
            try:
                registry.detach(key)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert not registry.is_known(key)


# ---------------------------------------------------------------------------
# _make_settings (requires Qt)
# ---------------------------------------------------------------------------

class RealSettingsRegistry(ControllerRegistry):
    """Uses real _make_settings; injects FakeThread so no hardware starts."""

    def _make_thread(self, plugin_class, settings):
        return FakeThread()


class TestMakeSettings:
    """ControllerRegistry._make_settings passes all plugin params through."""

    def test_all_params_included(self, qapp):
        pc = make_plugin_class(params=[
            {'name': 'voltage', 'type': 'float', 'value': 0.0},
            {'name': 'speed', 'type': 'float', 'value': 1.0},
        ])
        reg = RealSettingsRegistry()
        _, hw = reg.attach(key_for(pc), pc)
        names = {ch.name() for ch in hw.children()}
        assert {'voltage', 'speed'}.issubset(names)
        reg.close_all()

    def test_params_state_restores_values(self, qapp):
        pc = make_plugin_class(params=[
            {'name': 'voltage', 'type': 'float', 'value': 0.0},
        ])
        reg = RealSettingsRegistry()
        from pymodaq_gui.parameter import Parameter
        dummy = Parameter.create(name='hw', type='group', children=[
            {'name': 'voltage', 'type': 'float', 'value': 3.3},
        ])
        _, hw = reg.attach(key_for(pc), pc, params_state=dummy.saveState())
        assert hw['voltage'] == 3.3
        reg.close_all()

    def test_exclude_params_strips_top_level_node(self, qapp):
        """Per-channel params must not appear in hw_settings."""
        pc = make_plugin_class(params=[
            {'name': 'voltage', 'type': 'float', 'value': 0.0},
            {'name': 'units', 'type': 'str', 'value': 'mm'},
            {'name': 'epsilon', 'type': 'float', 'value': 0.01},
        ])
        reg = RealSettingsRegistry()
        _, hw = reg.attach(key_for(pc), pc,
                           exclude_params=frozenset({'units', 'epsilon'}))
        names = {ch.name() for ch in hw.children()}
        assert 'voltage' in names
        assert 'units' not in names
        assert 'epsilon' not in names
        reg.close_all()

    def test_exclude_params_strips_nested_child(self, qapp):
        """('controller', 'axis') must remove only the axis child, keeping controller_ID."""
        pc = make_plugin_class(params=[
            {'name': 'voltage', 'type': 'float', 'value': 0.0},
            {'name': 'controller', 'type': 'group', 'children': [
                {'name': 'controller_ID', 'type': 'int', 'value': 0},
                {'name': 'axis', 'type': 'list', 'value': 'X'},
            ]},
        ])
        reg = RealSettingsRegistry()
        _, hw = reg.attach(key_for(pc), pc,
                           exclude_params=frozenset({('controller', 'axis')}))
        names = {ch.name() for ch in hw.children()}
        assert 'controller' in names
        ctrl_children = {ch.name() for ch in hw.child('controller').children()}
        assert 'controller_ID' in ctrl_children
        assert 'axis' not in ctrl_children
        reg.close_all()

    def test_legacy_flat_move_plugin_strips_per_channel(self, qapp):
        """Old-style flat Move plugins (no axis_settings group) have per-channel
        params stripped via LEGACY_PER_CHANNEL_NAMES when the caller passes
        exclude_params containing 'axis_settings' (the Move subscriber marker)."""
        pc = make_plugin_class(params=[
            {'name': 'voltage', 'type': 'float', 'value': 0.0},
            {'name': 'units', 'type': 'str', 'value': 'mm'},   # per-channel → stripped
        ])
        reg = RealSettingsRegistry()
        _, hw = reg.attach(key_for(pc), pc,
                           exclude_params=frozenset({'axis_settings'}))
        names = {ch.name() for ch in hw.children()}
        assert 'voltage' in names
        assert 'units' not in names   # stripped via LEGACY_PER_CHANNEL_NAMES
        reg.close_all()

    def test_viewer_plugin_strips_channel_settings_only(self, qapp):
        """Viewer plugins use the caller-provided exclude_params directly.
        channel_settings is stripped; hardware params are kept."""
        pc = make_plugin_class(params=[
            {'name': 'integration_time', 'type': 'float', 'value': 0.1},
            {'name': 'channel_settings', 'type': 'group', 'children': []},
        ])
        reg = RealSettingsRegistry()
        _, hw = reg.attach(key_for(pc), pc,
                           exclude_params=frozenset({'channel_settings'}))
        names = {ch.name() for ch in hw.children()}
        assert 'integration_time' in names
        assert 'channel_settings' not in names
        reg.close_all()

    def test_viewer_plugin_does_not_apply_legacy_move_exclusions(self, qapp):
        """A viewer plugin whose params happen to contain 'units' must NOT have
        it stripped — LEGACY_PER_CHANNEL_NAMES only fires for Move subscribers."""
        pc = make_plugin_class(params=[
            {'name': 'units', 'type': 'str', 'value': 'nm'},   # wavelength units — hw param for a spectrometer
            {'name': 'channel_settings', 'type': 'group', 'children': []},
        ])
        reg = RealSettingsRegistry()
        _, hw = reg.attach(key_for(pc), pc,
                           exclude_params=frozenset({'channel_settings'}))
        names = {ch.name() for ch in hw.children()}
        assert 'units' in names   # NOT stripped — not a Move subscriber
        assert 'channel_settings' not in names
        reg.close_all()

    def test_new_style_plugin_with_axis_settings_strips_group(self, qapp):
        """New-style plugins that already have an axis_settings group use the
        caller-provided exclude_params (frozenset({'axis_settings'}))."""
        pc = make_plugin_class(params=[
            {'name': 'voltage', 'type': 'float', 'value': 0.0},
            {'name': 'axis_settings', 'type': 'group', 'children': [
                {'name': 'units', 'type': 'str', 'value': 'mm'},
            ]},
        ])
        reg = RealSettingsRegistry()
        _, hw = reg.attach(key_for(pc), pc, exclude_params=frozenset({'axis_settings'}))
        names = {ch.name() for ch in hw.children()}
        assert 'voltage' in names
        assert 'axis_settings' not in names
        reg.close_all()


# ---------------------------------------------------------------------------
# strip_params (pure-Python, no Qt required)
# ---------------------------------------------------------------------------

class TestStripParams:
    """strip_params must remove named nodes and handle nested paths."""

    def _p(self, name, children=None):
        d = {'name': name, 'type': 'str'}
        if children is not None:
            d['children'] = children
        return d

    def test_empty_exclude_returns_all(self):
        params = [self._p('a'), self._p('b')]
        assert strip_params(params, frozenset()) == params

    def test_top_level_name_stripped(self):
        params = [self._p('units'), self._p('voltage')]
        result = strip_params(params, frozenset({'units'}))
        assert [p['name'] for p in result] == ['voltage']

    def test_multiple_top_level_stripped(self):
        params = [self._p('units'), self._p('epsilon'), self._p('voltage')]
        result = strip_params(params, frozenset({'units', 'epsilon'}))
        assert [p['name'] for p in result] == ['voltage']

    def test_nested_path_strips_child_keeps_parent(self):
        controller = self._p('controller', children=[
            self._p('controller_ID'),
            self._p('axis'),
        ])
        params = [self._p('voltage'), controller]
        result = strip_params(params, frozenset({('controller', 'axis')}))
        names = [p['name'] for p in result]
        assert 'voltage' in names
        assert 'controller' in names
        ctrl = next(p for p in result if p['name'] == 'controller')
        child_names = [c['name'] for c in ctrl['children']]
        assert 'controller_ID' in child_names
        assert 'axis' not in child_names

    def test_does_not_mutate_original(self):
        controller = self._p('controller', children=[
            self._p('controller_ID'),
            self._p('axis'),
        ])
        params = [controller]
        _ = strip_params(params, frozenset({('controller', 'axis')}))
        # Original must be untouched.
        orig_children = [c['name'] for c in controller['children']]
        assert 'axis' in orig_children

    def test_unknown_name_is_noop(self):
        params = [self._p('voltage')]
        result = strip_params(params, frozenset({'nonexistent'}))
        assert [p['name'] for p in result] == ['voltage']

    def test_combined_top_and_nested(self):
        """Units (top-level) and axis (nested) are both stripped; voltage and
        controller_ID survive."""
        controller = self._p('controller', children=[
            self._p('controller_ID'),
            self._p('axis'),
        ])
        params = [self._p('units'), self._p('voltage'), controller]
        result = strip_params(
            params,
            frozenset({'units', ('controller', 'axis')}),
        )
        top_names = [p['name'] for p in result]
        assert top_names == ['voltage', 'controller']
        ctrl = next(p for p in result if p['name'] == 'controller')
        child_names = [c['name'] for c in ctrl['children']]
        assert child_names == ['controller_ID']
