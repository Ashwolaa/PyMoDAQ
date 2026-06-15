# Capabilities API for `feature/controller-thread-architecture`

> **Note**: this supersedes the earlier draft of this document (Phases 0–5 /
> CT-1..CT-3b below this point described a full `ChannelControl` +
> `HardwareWidget` + `DAQ_Monitor` rebuild on top of the controller-thread
> work). The controller-thread architecture itself is now done — see
> `CONTROLLER_THREAD_PLAN.md`. After reviewing the prototype on
> `feature/capabilities`, the scope has been narrowed considerably (see
> below). The old phase list is kept at the bottom for historical reference
> only; do not use it as a task list.

## Context

`feature/capabilities` is a sibling branch (same merge-base as the current
branch) that independently rewrote `daq_move`/`daq_viewer`/etc. A direct
merge is not viable (real conflicts in 4 core files + icon resources).
Reviewing that branch slice-by-slice:

- `DAQ_HardwareWorker` — **redundant**. `ControllerThread`'s new-style
  dispatch (`_is_new_style`, `_on_group_tick`/`_solo_tick`,
  `request_read`/`request_snap`/`request_write`) already covers it. Drop.
- `ChannelControl` + `compact_dock_manager` changes — UI scope creep,
  overlaps with the separate "Settings-as-DAQ" idea (see LECO actor plan).
  Defer.
- `capabilities.py` (Observable/Variable/ContinuousVariable/DiscreteVariable/
  Capabilities/infer_capabilities — pure dataclasses, 332 lines) — **this is
  what we want**, for use when writing new plugins.
- `plugin_base.py` (`DAQ_Plugin_base`) — **redundant**. Its non-capabilities
  responsibilities (settings tree, `send_param_status`/`update_settings`,
  `is_master`, `ini_controller_init`, `commit_settings`, `emit_status`) are
  *already* implemented by `PluginBase` in
  `packages/pymodaq/src/pymodaq/control_modules/utils.py:704`.

Crucially, `controller_thread.py:961-963` already has dead-but-ready code:
```python
caps = getattr(plugin, 'capabilities', None)
if caps is not None:
    self.capabilities_signal.emit(caps)
```
This fires once during `_ini_new_style()`. Today nothing sets `.capabilities`,
so it never emits. Porting `capabilities.py` + wiring a `capabilities`
property activates this path for both new-style plugins and (for free)
existing old-style plugins.

## Changes

### 1. Port `capabilities.py` (verbatim, pure Python)
New file: `packages/pymodaq/src/pymodaq/control_modules/capabilities.py`
- Copy from `pr/capabilities/2-plugin-base:packages/pymodaq/src/pymodaq/control_modules/capabilities.py`
  (332 lines) essentially as-is — `Observable`, `Variable`,
  `ContinuousVariable`, `DiscreteVariable`, `Capabilities`,
  `infer_capabilities`, `_variable_from_dict`/`_KIND_MAP`.
- No changes needed: zero dependencies on anything else in PyMoDAQ (no Qt, no
  `plugin_base.py`).

### 2. Port its test suite (verbatim)
New file: `packages/pymodaq/tests/control_modules/test_capabilities.py`
- Copy from `pr/capabilities/2-plugin-base:packages/pymodaq/tests/control_modules/test_capabilities.py`
  (413 lines, pure pytest, no Qt fixtures needed).

### 3. Add a lazy `capabilities` property to `PluginBase`
File: `packages/pymodaq/src/pymodaq/control_modules/utils.py` (class
`PluginBase`, ~line 704)
- Add a property mirroring the one in
  `pr/capabilities/2-plugin-base:.../plugin_base.py` (lazy infer + cache +
  re-entrancy guard), but **trimmed**: getter only (no
  `capabilities_updated_signal`/setter — that's part of the deferred
  `ChannelControl` wiring).

```python
@property
def capabilities(self) -> 'Capabilities':
    """Lazily inferred hardware capabilities (see infer_capabilities)."""
    caps = self.__dict__.get('_capabilities')
    if caps is not None:
        return caps
    if self.__dict__.get('_caps_computing'):
        return None
    self.__dict__['_caps_computing'] = True
    try:
        from pymodaq.control_modules.capabilities import infer_capabilities
        result = infer_capabilities(self)
        self.__dict__['_capabilities'] = result
        return result
    finally:
        self.__dict__['_caps_computing'] = False
```

- Effect: `DAQ_Move_base` subclasses (which already set
  `_axis_names`/`_controller_units`/`_epsilons`) get `ContinuousVariable`-based
  capabilities inferred automatically; `DAQ_Viewer_base` subclasses get the
  `Observable('data')` fallback. New plugins built on `PluginBase` get this
  for free too, or can override by declaring a class-level
  `capabilities = Capabilities(...)` (a plain class attribute on the subclass
  shadows the base property — no conflict).
- Local import inside the property avoids any import-order/circularity
  concerns (`capabilities.py` imports nothing from `utils.py`).

### 4. Test the new property
File: `packages/pymodaq/tests/control_modules/cont_mod_utils_test.py`
- Add a new `TestPluginBaseCapabilities` class:
  - A `PluginBase` subclass with no special attrs → `capabilities` returns
    `Capabilities(observables=[Observable('data')], ...)` (detector
    fallback).
  - A subclass setting `_axis_names`/`_controller_units`/`_epsilons` →
    `capabilities.variables` contains matching `ContinuousVariable`(s).
  - Result is cached (`is` identity across two accesses).
  - A subclass declaring its own class-level `capabilities = Capabilities(...)`
    → property is shadowed, returns that instance directly.

### 5. Update `controller_thread.py` docstring (small)
File: `packages/pymodaq/src/pymodaq/control_modules/controller_thread.py`
(~line 75-81)
- The "New-style plugin interface (future)" docstring section currently lists
  `open/close/query_data/change_to` with no mention of capabilities. Add one
  line + a tiny example showing a new-style plugin can declare:

```python
capabilities: ClassVar[Capabilities] = Capabilities(
    variables=[ContinuousVariable(name='x', lo=0, hi=10, epsilon=0.01)],
)
```

  pointing to `pymodaq.control_modules.capabilities`. Documentation-only
  change, no behavior change — existing `test_controller_thread.py` tests
  (`test_ini_emits_capabilities_when_present`, using `fake_caps = object()`)
  already cover the emission wiring and need no edits.

## What is explicitly NOT done

- No `DAQ_Plugin_base`, `DAQ_HardwareWorker`, `ChannelControl`, or
  `compact_dock_manager` changes.
- No new example/mock "new-style" plugin — `test_controller_thread.py`
  already has `MockPlugin` covering the new-style contract; `capabilities.py`
  is independently unit-tested.
- No changes to `move_utility_classes.py` / `viewer_utility_classes.py` beyond
  inheriting the new `PluginBase.capabilities` property.

## Verification

```bash
PYTHONPATH=/d/Work/PyMoDAQ/packages/pymodaq_utils/src:/d/Work/PyMoDAQ/packages/pymodaq_data/src:/d/Work/PyMoDAQ/packages/pymodaq_gui/src:/d/Work/PyMoDAQ/packages/pymodaq/src \
  python3 -m pytest packages/pymodaq/tests/control_modules/test_capabilities.py \
                     packages/pymodaq/tests/control_modules/cont_mod_utils_test.py \
                     packages/pymodaq/tests/control_modules/test_controller_thread.py -v
```

All new + existing tests should pass headlessly (no Qt widgets shown, `qapp`
fixture only).

---

## Historical context (superseded — kept for reference only)

The original draft of this document described a much larger rebuild:
`ChannelControl` toolbar rows, `compact_dock_manager` diffing,
`DAQ_Plugin_base` adapters, `ChannelScheduler`/`ControllerThread`,
`HardwareWidget`, preset-serialized capability selection, dynamic
capabilities from the parameter tree, and a `DAQ_Monitor` extension
(Phases 0–5, CT-1..CT-3b). The `ControllerThread`/`ControllerRegistry` work
(CT-1/CT-2) shipped as part of `CONTROLLER_THREAD_PLAN.md` instead. The
remaining items (`ChannelControl`, `HardwareWidget`, preset capability
selection, `param_to_capability`, `DAQ_Monitor`) are deferred indefinitely —
revisit only if/when a concrete need for per-channel generic UI rows arises,
and at that point reconcile with the "Settings-as-DAQ" approach from the LECO
actor plan rather than building both.
