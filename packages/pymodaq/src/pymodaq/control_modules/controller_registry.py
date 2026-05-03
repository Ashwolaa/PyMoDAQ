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


__all__ = ['ControllerKey', 'ControllerRegistry', 'COMMON_DAQ_PARAM_NAMES', 'strip_params']


def strip_params(params: list, exclude: 'frozenset') -> list:
    """Return a copy of *params* with excluded nodes removed.

    Parameters
    ----------
    params :
        List of pyqtgraph-style parameter dicts (each has at least
        ``'name'`` and optionally ``'children'``).
    exclude :
        Frozenset whose members are either:

        * ``str``   — remove any top-level node with that name.
        * ``tuple`` — hierarchical path: ``('group', 'child')`` removes
          ``child`` from within ``group``, keeping ``group`` itself.

    The function is applied recursively: nested path tuples are resolved
    level by level.  The input lists are not mutated.
    """
    if not exclude:
        return list(params)

    top = {e for e in exclude if isinstance(e, str)}
    nested = {e for e in exclude if isinstance(e, tuple) and len(e) >= 2}

    result = []
    for p in params:
        name = p.get('name', '')
        if name in top:
            continue
        # Collect child-level exclusions that pass through this node.
        child_excl = frozenset(
            e[1] if len(e) == 2 else e[1:]
            for e in nested if e[0] == name
        )
        if child_excl and p.get('children'):
            p = dict(p)  # shallow-copy the dict so we don't mutate the original
            p['children'] = strip_params(list(p['children']), child_excl)
        result.append(p)
    return result


# Keep the old private name as an alias during transition.
_strip_params = strip_params

# Top-level param names injected by comon_parameters / comon_parameters_fun
# that belong to the DAQ module (per-channel) rather than to the physical
# hardware.  Used by DAQ_Move._PER_CHANNEL_PARAMS to exclude these from the
# shared hw_settings relay so each module keeps its own axis/units/epsilon.
#
# Limitation: plugin authors must not reuse these names for hardware params.
COMMON_DAQ_PARAM_NAMES: frozenset = frozenset({
    'units', 'epsilon', 'timeout', 'bounds', 'scaling', 'controller',
})

# Per-channel param names used by old-style (flat) plugins.
# When a plugin's params do NOT contain an 'axis_settings' group, these
# names are used as the exclusion set for hw_settings instead of 'axis_settings'.
LEGACY_PER_CHANNEL_NAMES: frozenset = frozenset({
    'units', 'epsilon', 'timeout', 'bounds', 'scaling',
    ('controller', 'axis'),
})


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
    """Internal registry record for one active controller.

    ``settings`` is a dict keyed by plugin class so that a ``DAQ_Move`` and a
    ``DAQ_Viewer`` that share the same ``ControllerThread`` (same hardware) each
    get their own ``hw_settings`` ``Parameter`` built from their own plugin's
    params.  Two ``DAQ_Move`` instances on the same key share one entry in the
    dict (same plugin class → same ``Parameter``).
    """

    thread: Any          # ControllerThread in production; Any for test injection
    settings: dict       # {plugin_class: Parameter}
    ref_count: int = 1
    subscribers: dict = field(default_factory=dict)  # {id(obj): repr(obj)} — debug only
    hw_panels: dict = field(default_factory=dict)   # {plugin_class: QWidget}
    hw_actions: dict = field(default_factory=dict)  # {plugin_class: QAction}


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
        exclude_params: 'frozenset | None' = None,
    ) -> tuple[Any, 'Parameter']:
        """Return ``(thread, hw_settings)`` for *key*.

        **First caller** (key not yet known): creates the shared
        ``Parameter`` model in the calling thread (expected to be the
        GUI thread), creates and starts a ``ControllerThread``, stores
        the entry with ``ref_count=1``.

        **Subsequent callers** (key already known): increment
        ``ref_count`` and return the existing ``(thread, hw_settings)``
        pair.  *params_state* and *exclude_params* are ignored — the
        hardware and shared settings are already live.

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
        exclude_params :
            Frozenset of param names / path tuples to strip from the
            shared ``hw_settings`` Parameter.  Per-channel parameters
            (``units``, ``epsilon``, ``bounds``, ``scaling``, ``axis``
            selection) belong to each module's own settings tree, not to
            the shared hardware settings — pass the module's
            ``_PER_CHANNEL_PARAMS`` here.  Only applied on first attach.

        Returns
        -------
        thread :
            The ``ControllerThread`` owning the hardware.
        hw_settings :
            The ``Parameter`` model for *plugin_class* (lives in the GUI
            thread).  Contains only per-controller hardware parameters —
            per-channel parameters named in *exclude_params* are stripped.

            Each plugin class that attaches to the same key gets its own
            independent ``Parameter`` object built from that class's
            ``params``.  Two ``DAQ_Move`` instances (same plugin class)
            share the same object; a ``DAQ_Viewer`` on the same key gets
            a separate one derived from its own plugin params.
        """
        with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                entry.ref_count += 1
                if subscriber is not None:
                    entry.subscribers[id(subscriber)] = repr(subscriber)
                if plugin_class not in entry.settings:
                    # New plugin type attaching to an existing CT — build its
                    # own hw_settings from its own params.
                    entry.settings[plugin_class] = self._make_settings(
                        plugin_class, params_state,
                        exclude_params=exclude_params or frozenset(),
                    )
                return entry.thread, entry.settings[plugin_class]

            hw_settings = self._make_settings(
                plugin_class, params_state,
                exclude_params=exclude_params or frozenset(),
            )
            thread = self._make_thread(plugin_class, params_state)
            subs = {id(subscriber): repr(subscriber)} if subscriber is not None else {}
            self._entries[key] = _Entry(
                thread=thread,
                settings={plugin_class: hw_settings},
                subscribers=subs,
            )
            return thread, hw_settings

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
        self,
        plugin_class: type,
        params_state: dict | None,
        exclude_params: 'frozenset' = frozenset(),
    ) -> 'Parameter':
        """Create the shared ``Parameter`` model for the plugin.

        Only per-controller parameters are included.  Per-channel
        parameters listed in *exclude_params* (e.g. ``units``,
        ``epsilon``, ``bounds``, ``scaling``, ``axis`` selection) are
        stripped from the tree — each subscribing module owns its own
        per-channel copies in its local settings tree.

        The CT creates its own hardware-thread settings tree independently
        from the full ``plugin_class.params``; stripping nodes here does
        NOT affect the plugin's internal state or hardware initialisation.

        Called from :meth:`attach` with the registry lock held.
        The returned object lives in the GUI thread.
        """
        from pymodaq_gui.parameter import Parameter
        all_params = getattr(plugin_class, 'params', [])
        # Old-style Move plugins emit flat per-channel params (no 'axis_settings'
        # group).  Fall back to the legacy per-name exclusion set so hw_settings
        # is still stripped cleanly for those plugins.  The fallback only applies
        # when the caller is a Move subscriber (exclude_params contains
        # 'axis_settings'); Viewer subscribers use their own exclude_params
        # directly so that e.g. 'channel_settings' is correctly stripped.
        is_move_subscriber = 'axis_settings' in exclude_params
        has_axis_settings = any(
            p.get('name') == 'axis_settings' for p in all_params
        )
        effective_exclude = (
            LEGACY_PER_CHANNEL_NAMES
            if is_move_subscriber and not has_axis_settings
            else exclude_params
        )
        hw_params = _strip_params(list(all_params), effective_exclude)
        settings = Parameter.create(name='Settings', type='group',
                                    children=hw_params)
        if params_state is not None:
            settings.restoreState(params_state, addChildren=False,
                                  removeChildren=False)
        return settings

    def _make_thread(self, plugin_class: type, params_state: dict | None) -> Any:
        """Instantiate and start a ``ControllerThread`` for *plugin_class*.

        Receives *params_state* (a plain dict, safe to pass across threads)
        rather than the live ``Parameter`` object so the CT can create its own
        hardware-thread-owned settings tree inside ``ini_hardware``.

        Override in tests to inject a mock thread object::

            class FakeRegistry(ControllerRegistry):
                def _make_thread(self, plugin_class, params_state):
                    return FakeThread()

        Called from :meth:`attach` with the registry lock held.
        The ``ControllerThread`` import is deferred so Phase CT-1 tests
        can run before ``controller_thread.py`` exists.
        """
        from pymodaq.control_modules.controller_thread import ControllerThread  # noqa: PLC0415
        thread_obj = ControllerThread(plugin_class, params_state)
        import qtpy.QtCore as QtCore
        qt_thread = QtCore.QThread()
        thread_obj.moveToThread(qt_thread)
        # Do NOT connect started → ini_hardware here.
        # ini_hardware is triggered by ControllerThreadModule.init_hardware()
        # via QMetaObject.invokeMethod, AFTER all signal connections are made.
        # This guarantees settings_changed (e.g. units from ini_stage) is received
        # by subscribers even when hardware initialises quickly.
        thread_obj.parent_qt_thread = qt_thread  # keep reference; prevents GC while running
        qt_thread.start()
        return thread_obj

    # ------------------------------------------------------------------
    # Shared GUI objects (GUI thread only — no lock required)
    # ------------------------------------------------------------------

    def get_hw_panel(self, key: ControllerKey, plugin_class: type) -> Any:
        """Return the hw_settings panel for *key* + *plugin_class*, creating it if needed.

        Each plugin class on the same key gets its own floating ``QWidget``
        (Move shows Move hardware params; Viewer shows Viewer hardware params).

        Must be called from the GUI thread.  Returns ``None`` if *key* or
        *plugin_class* is not registered.
        """
        entry = self._entries.get(key)
        if entry is None or plugin_class not in entry.settings:
            return None
        if plugin_class not in entry.hw_panels:
            panel = self._make_hw_panel(entry.settings[plugin_class])
            action = self._make_hw_action(panel)
            entry.hw_panels[plugin_class] = panel
            entry.hw_actions[plugin_class] = action
        return entry.hw_panels[plugin_class]

    def get_hw_action(self, key: ControllerKey, plugin_class: type) -> Any:
        """Return the show/hide ``QAction`` for *key* + *plugin_class*.

        Must be called from the GUI thread.  Returns ``None`` if *key* or
        *plugin_class* is not registered.
        """
        entry = self._entries.get(key)
        if entry is None or plugin_class not in entry.settings:
            return None
        if plugin_class not in entry.hw_actions:
            self.get_hw_panel(key, plugin_class)  # creates both panel and action
        return entry.hw_actions[plugin_class]

    def _make_hw_panel(self, hw_settings: 'Parameter') -> Any:
        """Create a floating QWidget showing *hw_settings* in a ParameterTree.

        Override in tests or subclasses if Qt widgets are not available.
        """
        from qtpy.QtWidgets import QWidget, QVBoxLayout
        from pymodaq_gui.parameter import ParameterTree

        panel = QWidget()
        panel.setWindowTitle('Hardware Settings')
        tree = ParameterTree()
        tree.setParameters(hw_settings, showTop=False)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tree)
        panel.resize(300, 400)
        return panel

    def _make_hw_action(self, panel: Any) -> Any:
        """Create the shared checkable QAction that shows/hides *panel*.

        The panel's close event is patched to uncheck the action so that
        all toolbars stay in sync when the panel is dismissed via its
        window close button.

        Override in tests or subclasses if Qt widgets are not available.
        """
        from pymodaq_gui.utils.styling import create_icon
        from qtpy.QtWidgets import QAction

        action = QAction('Hardware Settings')
        action.setCheckable(True)
        action.setToolTip('Show/hide hardware settings (shared across all modules on this controller)')
        try:
            action.setIcon(create_icon('settings'))
        except Exception:
            pass

        action.toggled.connect(panel.setVisible)

        def _on_panel_close(event):
            action.setChecked(False)
            event.accept()

        panel.closeEvent = _on_panel_close
        return action

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
        # Close all per-plugin-class GUI panels that were created.
        for panel in list(entry.hw_panels.values()):
            try:
                panel.close()
            except Exception:
                pass
        entry.hw_panels.clear()
        entry.hw_actions.clear()
