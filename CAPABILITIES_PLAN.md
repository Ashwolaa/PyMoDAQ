# Capabilities-Driven Control Architecture — Implementation Plan

## Goal

Unify `DAQ_Move` and `DAQ_Viewer` around a two-method hardware interface
(`query_data` / `change_to`) driven by `Capabilities` metadata.  The UI is
assembled dynamically from what the plugin *declares*, not from which class it
inherits.

### Key concepts

- **`ChannelControl`** — lightweight per-channel unit (one per `Observable` or
  `Variable`).  Holds a toolbar row + two callables.  Replaces the full
  `DAQ_Move` / `DAQ_Viewer` instance as the unit of a compact-dock row.
- **`DAQ_Monitor`** — separate display dock; shows viewers for whichever
  channels the user selects.  Decoupled from the control layer.
- **`change_done_signal`** — plugin emits this when a `change_to` completes;
  base class provides a polling fallback so hardware without a native done
  interrupt still works.
- **Option B migration** — every phase leaves existing plugins working; old
  abstract methods (`grab_data`, `move_abs`, …) are deprecated gradually, not
  removed.

### Capabilities lifecycle

`capabilities` is a **live property**, not a one-time declaration.  It can
change at three points:

| When | Trigger | Example |
|------|---------|---------|
| Import time | Class attribute | `_controller_units = 'mm'` |
| After `ini()` | Hardware query | Camera reports actual sensor size |
| After `commit_settings()` | Parameter change | Binning → new shape; range → new lo/hi; mode switch → different channel set |

The plugin emits `capabilities_updated_signal(new_caps: Capabilities)` whenever
capabilities change.  The framework responds at two levels:

- **In-place refinement** (`ChannelControl.update_capability(new_cap)`) — same
  channel exists, metadata changed.  Updates spinbox bounds
  (`ContinuousVariable` lo/hi), repopulates combobox items (`DiscreteVariable`
  choices).  `Observable` shape changes are forwarded to `DAQ_Monitor` only
  (toolbar is unaffected).
- **Structural diff** — `capabilities_updated_signal` triggers a diff of old vs
  new `Capabilities`; new channels get new `ChannelControl` rows added to the
  compact dock, removed channels get their rows cleaned up.

Preset storage saves declared (class-level) capabilities so the dashboard can
reconstruct the full UI layout without hardware connected.  Confirmed
capabilities (post-`ini`) are not persisted — they are re-discovered on next
hardware init.

---

## Phase 0 — `ChannelControl` dataclass  ✅ COMPLETE

**New file:** `packages/pymodaq/src/pymodaq/control_modules/channel_control.py`

### Tasks

- [x] Define `ChannelControl` dataclass:
  - `capability: Observable | Variable`
  - `query: Callable[[], DataToExport]`
  - `change: Callable[[Any], None] | None`  (None for pure Observables)
  - `toolbar: Any`
- [x] Define `build_toolbar(capability) -> QToolBar` factory:
  - `Observable`            → Snap / Grab / Stop  (mirrors DAQ_Viewer toolbar)
  - `ContinuousVariable`    → label + spinbox + Go + readback display
  - `DiscreteVariable`      → label + combobox + Set
  - `Variable` (bool dtype) → toggle button
- [x] Backward-compat constructors (adapters, no plugin changes required):
  - `ChannelControl.from_daq_move(daq_move) -> ChannelControl`
  - `ChannelControl.from_daq_viewer(daq_viewer) -> ChannelControl`

### Tests

- `packages/pymodaq/tests/control_modules/test_capabilities.py` — 55 tests (restored from git)
- `packages/pymodaq/tests/control_modules/test_channel_control.py` — 72 passed, 16 skipped (Qt)
- `packages/pymodaq/tests/control_modules/conftest.py` — headless loader; stubs Qt-laden `__init__`

Qt tests (`TestBuildToolbar`) skipped when no backend; run in full Qt environments.

---

## Phase 1 — Capabilities-driven compact dock

**Modified file:** `packages/pymodaq/src/pymodaq/utils/compact_dock_manager.py`

### Tasks

- [ ] Extend `_RowData`: `module` type hint → `ChannelControl | DAQ_Move |
  DAQ_Viewer` (union, no removals)
- [ ] Add `add_channel(channel_control: ChannelControl)` to
  `ModuleCompactDock`, alongside existing `add_module()`
- [ ] `ActuatorCompactDock.add_channel()` — accepts `Variable`-typed
  `ChannelControl`; toolbar action names stay the same as `LOCKABLE_ACTIONS`
- [ ] `DetectorCompactDock.add_channel()` — accepts `Observable`-typed
  `ChannelControl`
- [ ] `_apply_lock` / `_update_alignment` — handle both `ChannelControl` rows
  and legacy module rows without branching everywhere (duck-type on `.toolbar`)

### Tests to update / add

`packages/pymodaq/tests/utils/test_compact_dock_manager.py` (update existing)

- Existing `add_module` tests must still pass unchanged
- Add: `add_channel` with `ContinuousVariable` → row appears in actuator dock
- Add: `add_channel` with `Observable` → row appears in detector dock
- Add: `_apply_lock` disables correct actions on `ChannelControl` rows
- Add: mixed dock (legacy module row + ChannelControl row) coexist

---

## Phase 2 — New plugin base class

**New file:** `packages/pymodaq/src/pymodaq/control_modules/plugin_base.py`

**Modified files:** `move_utility_classes.py`, `viewer_utility_classes.py`

### Tasks

- [ ] Define `DAQ_Plugin_base`:
  - Abstract: `query_data(names=None)`, `change_to(name, value)`, `ini()`,
    `close()`, `stop()`
  - Signal: `change_done_signal = Signal(str, DataToExport)`
  - Default polling fallback: `_poll_until_done(name, target, epsilon)` —
    called by base class after `change_to` if the plugin does not override done
    detection; stops when `|query_data([name]) - target| <= epsilon`
  - `capabilities: Capabilities` — class attribute required for new-style
    plugins; `infer_capabilities(self)` used as fallback
- [ ] `DAQ_Move_base(DAQ_Plugin_base)` — adapter methods with
  `DeprecationWarning`:
  - `get_actuator_value()` → delegates to `query_data()`
  - `move_abs(value)` → delegates to `change_to()`, triggers
    `_poll_until_done`
  - `move_rel(value)`, `move_home()` → same pattern
- [ ] `DAQ_Viewer_base(DAQ_Plugin_base)` — adapter methods:
  - `snap()` / `grab_data()` → delegate to `query_data()`
  - `dte_signal` still emitted (compatibility); wired from `query_data` return

Old abstract methods (`ini_stage`, `grab_data`, `move_abs`, `get_actuator_value`,
…) remain and still work — no existing plugin is broken.

### Tests to update / add

`packages/pymodaq/tests/control_modules/test_plugin_base.py` (new)

- `_poll_until_done` terminates when within epsilon, times out correctly
- `change_done_signal` emitted after polling resolves
- `DAQ_Move_base` adapter: calling `move_abs` on a new-style plugin that
  implements `change_to` works end-to-end
- `DAQ_Viewer_base` adapter: calling `grab_data` on a new-style plugin that
  implements `query_data` works end-to-end

`packages/pymodaq/tests/control_modules/test_move_utility_classes.py` (update)

- Existing tests still pass; no regressions from adapter addition

`packages/pymodaq/tests/control_modules/test_viewer_utility_classes.py` (update)

- Same: no regressions

---

## Phase 3 — Framework detection and unified hardware worker

**Modified files:** `daq_move.py`, `daq_viewer.py`

**New file:** `packages/pymodaq/src/pymodaq/control_modules/hardware_worker.py`

### Tasks

- [ ] `_is_new_style(plugin) -> bool`:
  - True if `plugin` implements `query_data` directly (not via the adapter
    shim inherited from `DAQ_Move_base` / `DAQ_Viewer_base`)
- [ ] `DAQ_HardwareWorker(QObject)` — single shared worker for new-style
  plugins:
  - Continuous monitoring loop: calls `query_data(watched_names)` at configured
    rate; replaces both the actuator refresh timer and the detector live-grab
    loop
  - Listens for `change_done_signal` from plugin; relays to main thread
  - Emits `data_ready_signal(DataToExport)` → consumed by `DAQ_Monitor`
- [ ] `DAQ_Move_Hardware.queue_command` — branch: old-style → existing path
  unchanged; new-style → `DAQ_HardwareWorker`
- [ ] `DAQ_Detector.queue_command` — same branch

### Tests to update / add

`packages/pymodaq/tests/control_modules/test_hardware_worker.py` (new)

- Monitoring loop emits `data_ready_signal` at correct rate (mock plugin)
- `change_done_signal` relayed correctly
- Old-style plugin routed through old code path (no regression)

`packages/pymodaq/tests/control_modules/test_daq_move.py` (update)

- New-style plugin goes through `DAQ_HardwareWorker`, not `DAQ_Move_Hardware`
- Old-style plugin still works via `DAQ_Move_Hardware`

`packages/pymodaq/tests/control_modules/test_daq_viewer.py` (update)

- Same pattern as above for `DAQ_Detector`

---

## Phase 4 — Dynamic capabilities from parameter tree

**New file:** `packages/pymodaq/src/pymodaq/control_modules/param_to_capability.py`

**Modified files:** `move_utility_classes.py`, `viewer_utility_classes.py` (or
shared parameter tree widget)

### Tasks

- [ ] `param_to_capability(param) -> Observable | Variable`:
  - `float` / `int` param → `ContinuousVariable`; reads `limits` for `lo`/`hi`
  - `list` param → `DiscreteVariable`; reads `values` for `choices`
  - `bool` param → `Variable` (dtype `'bool'`)
  - anything else → `Observable`
- [ ] Right-click context menu on parameter tree nodes:
  - "Expose as Observable" / "Expose as Variable"
  - Calls `param_to_capability`, appends to `plugin.capabilities`
  - Emits `capabilities_changed_signal` on plugin
- [ ] Dashboard / compact dock manager listens to `capabilities_changed_signal`
  → creates new `ChannelControl` → calls `add_channel()` on the right dock

### Tests to update / add

`packages/pymodaq/tests/control_modules/test_param_to_capability.py` (new)

- Each param type maps to the correct capability subclass
- `lo`/`hi` from `limits` is preserved in `ContinuousVariable`
- `choices` from list param preserved in `DiscreteVariable`

`packages/pymodaq/tests/control_modules/test_capabilities.py` (update existing,
55 tests)

- Add: round-trip `param → capability → toolbar` produces correct widget type

---

## Phase 5 — DAQ_Monitor

**New file:** `packages/pymodaq/src/pymodaq/control_modules/daq_monitor.py`

### Tasks

- [ ] `DAQ_Monitor(CustomApp)` — dockable display panel:
  - Channel list: checkboxes for every `Observable` / `Variable` across all
    loaded plugins
  - On check → opens viewer sized by `capability.shape` and `capability.dtype`
    (routes: scalar → Viewer0D, 1-D → Viewer1D, 2-D → Viewer2D)
  - Subscribes to `DAQ_HardwareWorker.data_ready_signal` for live feed
  - On uncheck → closes viewer, unsubscribes
- [ ] Replace the inline viewer management currently inside `DAQ_Viewer` with
  `DAQ_Monitor` (keep legacy path for old-style plugins until deprecation)
- [ ] Dashboard wiring: `ModulesManager` registers plugin capabilities with
  `DAQ_Monitor` on load/unload

### Tests to add

`packages/pymodaq/tests/control_modules/test_daq_monitor.py` (new)

- Channel list populated from capabilities
- Viewer opened/closed on check/uncheck
- Correct viewer type chosen by shape
- Data fed from mock `data_ready_signal`

---

## Migration guarantee (Option B — throughout all phases)

| Phase | Old plugins | New plugins |
|-------|-------------|-------------|
| 0–1   | Unaffected; compact dock still accepts legacy `add_module()` | Can use `ChannelControl` directly |
| 2     | Old abstract methods work; `DeprecationWarning` added | Implement `query_data`/`change_to` only |
| 3     | Routed through existing `DAQ_Move_Hardware`/`DAQ_Detector` | Routed through `DAQ_HardwareWorker` |
| 4–5   | New UI features available but not required | Full dynamic capabilities |
| Future | Remove deprecated methods after sufficient window | — |

**Rule:** every PR that touches a phase must run the full existing test suite
and must not introduce new failures.  New tests are added in the same PR as the
feature they cover.

---

## Starting point

Phase 0 is self-contained (pure Python + optional Qt for toolbar tests),
touches no existing code, and produces something immediately useful.  Start
there.
