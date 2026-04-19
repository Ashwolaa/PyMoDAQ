"""Process-global registry mapping controller keys to ControllerThread instances.

One ``ControllerThread`` is created per unique ``ControllerKey``
(hardware class + user-assigned controller ID).  Subsequent callers
that share the same key receive the already-running thread and the shared
``Parameter`` (hw_settings) model.  The thread is torn down when the last
subscriber detaches.

Usage
-----
Typical call site in ``DAQ_Move.init_hardware``::

    hw_cls = getattr(plugin_class, 'hardware_class', plugin_class)
    key = ControllerKey(
        hardware_class=hw_cls,
        controller_id=self.settings['main_settings', 'controller_ID'],
    )
    thread, hw_settings = ControllerRegistry.get().attach(
        key, plugin_class,
        params_state=self.settings.child(self._hw_settings_name).saveState(),
        subscriber=self,
    )

And in ``DAQ_Move.close``::

    ControllerRegistry.get().detach(key, subscriber=self)

Test isolation
--------------
Pass a fresh ``ControllerRegistry()`` instance to objects under test and
call ``registry.close_all()`` in teardown::

    registry = ControllerRegistry()
    # ... pass to DAQ_Move constructors ...
    registry.close_all()
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Optional

if TYPE_CHECKING:
    from pymodaq_gui.parameter import Parameter


__all__ = ['ControllerKey', 'ControllerRegistry']


@dataclass(frozen=True)
class ControllerKey:
    """Immutable, hashable key identifying one physical controller.

    Parameters
    ----------
    hardware_class :
        The underlying SDK / driver class (e.g. ``BeamSteering``).
        Plugins that share the same physical hardware declare the same
        ``hardware_class``; the registry maps this to one ``ControllerThread``.
        Plugins without a ``hardware_class`` attribute fall back to using
        the plugin class itself, giving it an exclusive thread.
    controller_id :
        User-assigned grouping integer (0–9999) from the parameter tree.
        Scoped within ``hardware_class``; two different hardware classes may
        share the same integer without collision.
    """

    hardware_class: type
    controller_id: int


@dataclass
class _Entry:
    """Internal registry record for one active controller."""

    thread: Any          # ControllerThread in production; Any for test injection
    settings: 'Parameter'
    ref_count: int = 1
    subscribers: dict = field(default_factory=dict)  # {id(obj): repr(obj)} — debug only


class ControllerRegistry:
    """Map ``ControllerKey`` → ``(ControllerThread, Parameter)``.

    Thread-safe: ``attach`` and ``detach`` may be called from any Qt
    thread (the GUI thread is typical but not guaranteed).

    In production use the module-level singleton via :meth:`get`.
    For test isolation, create a fresh instance per test.
    """

    # Module-level singleton and its creation lock.
    _global: ClassVar[ControllerRegistry | None] = None
    _global_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._entries: dict[ControllerKey, _Entry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton accessor
    # ------------------------------------------------------------------

    @classmethod
    def get(cls) -> ControllerRegistry:
        """Return the process-global singleton registry."""
        with cls._global_lock:
            if cls._global is None:
                cls._global = cls()
            return cls._global

    @classmethod
    def _reset_global(cls) -> None:
        """Replace the global singleton with a fresh instance.

        **For tests only.**  Calling this in production risks leaving
        dangling threads — use :meth:`close_all` first.
        """
        with cls._global_lock:
            cls._global = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def attach(
        self,
        key: ControllerKey,
        plugin_class: type,
        params_state: dict | None = None,
        subscriber: object | None = None,
    ) -> tuple[Any, 'Parameter']:
        """Return ``(thread, hw_settings)`` for *key*.

        **First caller** (key not yet known): creates the shared
        ``Parameter`` model in the calling thread (expected to be the
        GUI thread), creates and starts a ``ControllerThread``, stores
        the entry with ``ref_count=1``.

        **Subsequent callers** (key already known): increment
        ``ref_count`` and return the existing ``(thread, hw_settings)``
        pair.  *params_state* is ignored — the hardware is already live.

        Parameters
        ----------
        key :
            Unique controller identifier.
        plugin_class :
            The plugin *class* (not an instance).  Used to create the
            ``Parameter`` tree from ``plugin_class.params`` and to
            instantiate the plugin inside the hardware thread.
        params_state :
            Saved parameter state (``dict`` from ``Parameter.saveState()``
            or ``None``).  Only used on the first ``attach``; ignored
            by guests.
        subscriber :
            Optional reference to the calling object (e.g. a ``DAQ_Move``
            instance).  Stored in ``entry.subscribers`` for introspection
            and debugging only — not used for lifecycle logic.

        Returns
        -------
        thread :
            The ``ControllerThread`` owning the hardware.
        hw_settings :
            The shared ``Parameter`` model (lives in the GUI thread).
        """
        with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                entry.ref_count += 1
                if subscriber is not None:
                    entry.subscribers[id(subscriber)] = repr(subscriber)
                return entry.thread, entry.settings

            settings = self._make_settings(plugin_class, params_state)
            thread = self._make_thread(plugin_class, settings)
            subs = {id(subscriber): repr(subscriber)} if subscriber is not None else {}
            self._entries[key] = _Entry(thread=thread, settings=settings, subscribers=subs)
            return thread, settings

    def detach(self, key: ControllerKey, subscriber: object | None = None) -> None:
        """Decrement ref-count for *key*; tear down when it reaches zero.

        Safe to call even if *key* is unknown (no-op).

        Parameters
        ----------
        key :
            Unique controller identifier.
        subscriber :
            The same object passed to :meth:`attach`.  Removed from the
            debug subscribers dict if present.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return
            entry.ref_count -= 1
            if subscriber is not None:
                entry.subscribers.pop(id(subscriber), None)
            if entry.ref_count <= 0:
                self._teardown(entry)
                del self._entries[key]

    def ref_count(self, key: ControllerKey) -> int:
        """Return the current subscriber count for *key* (0 if unknown)."""
        with self._lock:
            entry = self._entries.get(key)
            return entry.ref_count if entry is not None else 0

    def is_known(self, key: ControllerKey) -> bool:
        """Return ``True`` if *key* has at least one active subscriber."""
        with self._lock:
            return key in self._entries

    def subscribers(self, key: ControllerKey) -> dict:
        """Return a snapshot of the debug subscribers dict for *key*.

        Keys are ``id(subscriber)``, values are ``repr(subscriber)``.
        Returns an empty dict if *key* is unknown.  For introspection only.
        """
        with self._lock:
            entry = self._entries.get(key)
            return dict(entry.subscribers) if entry is not None else {}

    def close_all(self) -> None:
        """Tear down all active threads regardless of ref-count.

        Intended for application shutdown and test teardown.
        """
        with self._lock:
            for entry in list(self._entries.values()):
                self._teardown(entry)
            self._entries.clear()

    # ------------------------------------------------------------------
    # Extension points (override in tests or subclasses)
    # ------------------------------------------------------------------

    def _make_settings(
        self, plugin_class: type, params_state: dict | None
    ) -> 'Parameter':
        """Create the shared ``Parameter`` model.

        Called from :meth:`attach` with the registry lock held.
        The returned object will live in whichever thread calls
        ``acquire`` (expected: GUI thread).
        """
        from pymodaq_gui.parameter import Parameter
        settings = Parameter.create(
            name='Settings', type='group',
            children=getattr(plugin_class, 'params', []),
        )
        if params_state is not None:
            settings.restoreState(params_state)
        return settings

    def _make_thread(self, plugin_class: type, settings: 'Parameter') -> Any:
        """Instantiate and start a ``ControllerThread`` for *plugin_class*.

        Override in tests to inject a mock thread object::

            class FakeRegistry(ControllerRegistry):
                def _make_thread(self, plugin_class, settings):
                    return FakeThread()

        Called from :meth:`attach` with the registry lock held.
        The ``ControllerThread`` import is deferred so Phase CT-1 tests
        can run before ``controller_thread.py`` exists.
        """
        from pymodaq.control_modules.controller_thread import ControllerThread  # noqa: PLC0415
        thread_obj = ControllerThread(plugin_class, settings)
        import qtpy.QtCore as QtCore
        qt_thread = QtCore.QThread()
        thread_obj.moveToThread(qt_thread)
        qt_thread.started.connect(thread_obj.ini_hardware)
        thread_obj.parent_qt_thread = qt_thread  # keep reference; prevents GC while running
        qt_thread.start()
        return thread_obj

    def _teardown(self, entry: _Entry) -> None:
        """Stop the hardware thread associated with *entry*.

        Called from :meth:`detach` and :meth:`close_all` with the
        registry lock held.
        """
        thread_obj = entry.thread
        # Ask the ControllerThread to close hardware gracefully.
        if hasattr(thread_obj, 'close_hardware'):
            thread_obj.close_hardware()
        # Stop the underlying QThread if there is one.
        qt_thread = getattr(thread_obj, 'parent_qt_thread', None)
        if qt_thread is not None and qt_thread.isRunning():
            qt_thread.quit()
            qt_thread.wait(2000)
