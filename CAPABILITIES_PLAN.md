# Capabilities-Driven Control Architecture — Implementation Plan

## Status summary

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | `ChannelControl` dataclass + toolbar factory | ✅ Done on `feature/capabilities` |
| 1 | Capabilities-driven compact dock | ✅ Done on `feature/capabilities` |
| 2 | `DAQ_Plugin_base` + adapters in `DAQ_Move_base` / `DAQ_Viewer_base` | ✅ Done on `feature/capabilities` |
| 3 | `DAQ_HardwareWorker` per plugin | ✅ Done — **superseded by ControllerThread** (see below) |
| CT-1 | `ControllerRegistry` | 🔲 Next |
| CT-2 | `ControllerThread` + `ChannelScheduler` | 🔲 Next |
| CT-3a | `DAQ_Move` / `DAQ_Viewer` as thin subscribers | 🔲 Next |
| CT-3b | `HardwareWidget` (shared QActions, status indicator) | 🔲 Follow-on |
| 3.5 | Preset serialization of capability selection | 🔲 Pending CT-3a |
| 4 | Dynamic capabilities from parameter tree | 🔲 Pending 3.5 |
| 5 | `DAQ_Monitor` | 🔲 Pending CT-3a |

All phases 0–3 were prototyped on `feature/capabilities`. They will be **rebuilt
cleanly** on top of `feature/cleaning/control-module-factorization` because the
capabilities branch history is too messy to merge directly.

---

## Relationship to ControllerThread plan

See `CONTROLLER_THREAD_PLAN.md` for the full threading architecture. The key
intersection with capabilities:

- **`ChannelScheduler`** (renamed from `DAQ_HardwareWorker`) moves from being a
  per-plugin instance into `ControllerThread`, where it serves all subscribers
  of one physical controller. Phase 3 (DAQ_HardwareWorker) is superseded by
  CT-2 (ControllerThread + ChannelScheduler).
- **`ChannelControl`** rows connect their snap/grab/stop actions to
  `ControllerThread` slots instead of a per-module worker.
- **`capabilities_updated_signal`** is still emitted by the plugin and relayed
  by `ControllerThread` to all subscribers; the compact dock diff logic
  (Phase 1) is unchanged.
- **`HardwareWidget`** (CT-3b) becomes the UI home for the init/settings actions
  that currently live in each DAQ toolbar.

---

## Goal

Unify `DAQ_Move` and `DAQ_Viewer` around a two-method hardware interface
(`query_data` / `change_to`) driven by `Capabilities` metadata. The UI is
assembled dynamically from what the plugin *declares*, not from which class it
inherits.

### Key concepts

- **`ChannelControl`** — lightweight per-channel unit (one per `Observable` or
  `Variable`). Holds a toolbar row + two callables. Replaces the full
  `DAQ_Move` / `DAQ_Viewer` instance as the unit of a compact-dock row.
- **`DAQ_Monitor`** — separate display dock; shows viewers for whichever
  channels the user selects. Decoupled from the control layer.
- **`change_done_signal`** — plugin emits this when a `change_to` completes;
  base class provides a polling fallback so hardware without a native done
  interrupt still works.
- **Option B migration** — every phase leaves existing plugins working; old
  abstract methods (`grab_data`, `move_abs`, …) are deprecated gradually, not
  removed.

### Capabilities lifecycle

`capabilities` is a **live property**, not a one-time declaration. It can
change at three points:

| When | Trigger | Example |
|------|---------|---------|
| Import time | Class attribute | `_controller_units = 'mm'` |
| After `ini()` | Hardware query | Camera reports actual sensor size |
| After `commit_settings()` | Parameter change | Binning → new shape; mode switch → different channel set |

The plugin emits **`capabilities_updated_signal(new_caps: Capabilities)`**
whenever capabilities change. `ControllerThread` relays this to all subscribers.
The compact dock responds with either an in-place update (`update_capability`)
or a structural diff (add/remove rows).

### Selection and acquisition are separate concerns

**Selected** means a `ChannelControl` row exists and is subscribed to
`ControllerThread.data_ready`. No hardware activity occurs from selection alone.

**Acquisition** is event-driven:

| User action | ControllerThread behaviour |
|-------------|--------------------------|
| Snap | one-shot `request_read(channel)`; result on `data_ready` |
| Grab | `start_grab(channel, continuous=True)`; ticks until `stop_grab` |
| Stop | `stop_grab(channel)` |
| Readback display | reads `ChannelScheduler.get_cached(channel)` — no hardware call |

`ChannelScheduler` tracks `grabbed_names: set[str]`. Outside an active grab,
the thread is idle for that channel.

Preset storage saves **declared (class-level) capabilities** and the
**deselected set**. Confirmed capabilities (post-`ini` hardware query) are
re-discovered via `capabilities_updated_signal` on next init.

---

## Phase 0 — `ChannelControl` dataclass ✅ COMPLETE

**New file:** `packages/pymodaq/src/pymodaq/control_modules/channel_control.py`

### What was done

- `ChannelControl` dataclass: `capability`, `query`, `change`, `toolbar`
- `build_toolbar(capability) -> QToolBar` factory:
  - `Observable` → Snap / Grab / Stop
  - `ContinuousVariable` → label + spinbox + Go + readback display
  - `DiscreteVariable` → label + combobox + Set
  - `Variable` (bool dtype) → toggle button
- Backward-compat constructors:
  - `ChannelControl.from_daq_move(daq_move)`
  - `ChannelControl.from_daq_viewer(daq_viewer)`
- Tests: 72 passed, 16 skipped (Qt)

### What changes in rebuild

`ChannelControl.query` and `ChannelControl.change` callables will be wired to
`ControllerThread` slots instead of a local worker. The dataclass itself is
unchanged; only the wiring site (Phase CT-3a) changes.

---

## Phase 1 — Capabilities-driven compact dock ✅ COMPLETE

**Modified files:** `compact_dock_manager.py`, `channel_control.py`

### What was done

- `_RowData` gains `channel_control` field (mutually exclusive with `module`)
- `channel_controls` property on `ModuleCompactDock`
- `ChannelControl.set_locked(locked)` — disables interactive widgets by
  `objectName`
- `_apply_lock` extended for `ChannelControl` rows
- `add_channel(cc)` / `remove_channel(name)` on `ModuleCompactDock`
- `_channel_rows: dict[str, ChannelControl]` for O(1) lookup by name
- `_on_capabilities_updated(new_caps)` — diff logic (add/remove/update rows);
  **not wired** here (wiring is in CT-3a where `ControllerThread` relays the
  signal)
- `update_capability(new_cap)` — in-place metadata refresh (spinbox bounds,
  combobox items)
- Tests: updated `compact_dock_manager_test.py`

### What changes in rebuild

`_on_capabilities_updated` is wired from `ControllerThread.capabilities_signal`
in Phase CT-3a instead of from a per-module `DAQ_Move.capabilities_updated_signal`.
No structural change to the dock itself.

---

## Phase 2 — `DAQ_Plugin_base` + adapters ✅ COMPLETE

**New file:** `packages/pymodaq/src/pymodaq/control_modules/plugin_base.py`

**Modified files:** `move_utility_classes.py`, `viewer_utility_classes.py`

### What was done

- `DAQ_Plugin_base(QObject)`:
  - `query_data(names, fresh)` / `change_to(name, value)` stubs
  - `_new_style_plugin: ClassVar[bool] = True`
  - `capabilities_updated_signal = Signal(object)`
  - `change_done_signal = Signal(str, object)`
  - `_poll_until_done(...)` polling fallback
  - `capabilities` property (lazy infer + cache + setter emits signal)
  - Shared `__init__`: settings tree, parent, title, controller, status
  - `send_param_status` / `update_settings` / `_apply_settings`
  - `is_master` property, `_init_controller` helper
- `DAQ_Move_base(DAQ_Plugin_base)`:
  - `_new_style_plugin = False` (old-style adapter)
  - `query_data()` wraps `get_actuator_value()` → `DataToExport`
  - `change_to(name, value)` delegates to `move_abs(value)`
- `DAQ_Viewer_base(DAQ_Plugin_base)`:
  - `_new_style_plugin = False`
  - `query_data()` delegates to `parent.snap()` when in hardware thread
- Naming aliases (Phase 0 of ControllerThread plan):
  - `PluginBase = DAQ_Plugin_base`
  - `ActuatorPlugin = DAQ_Move_base`
  - `DetectorPlugin = DAQ_Viewer_base`
- Tests: `test_plugin_base.py`

### What changes in rebuild

Signal relay chain (`capabilities_updated_signal` from plugin → hardware worker
→ DAQ module → dashboard) is simplified: `ControllerThread` relays directly to
all subscribers. The per-module relay wiring in `DAQ_Move_Hardware`,
`DAQ_Move`, `DAQ_Detector`, `DAQ_Viewer`, `dashboard.py` is removed and
replaced by `ControllerThread`'s broadcast in Phase CT-3a.

---

## Phase 3 — `DAQ_HardwareWorker` ✅ DONE — superseded by CT-2

**New file:** `hardware_worker.py` (to be replaced by `controller_thread.py`)

`DAQ_HardwareWorker` was implemented as a per-plugin demand-driven worker with
`snap`, `grab`, `stop`, `get_cached`, `change_to`. This is the right API but
the wrong scope — it serialises within one plugin's thread but does not prevent
cross-module conflicts when two DAQ modules share a physical controller.

**Superseded by**: `ChannelScheduler` (same API, renamed) inside
`ControllerThread` (Phase CT-2). `ChannelScheduler` is a child `QObject` of
`ControllerThread` so it shares the hardware thread and naturally serialises
all channel access across all subscribers.

`_is_new_style(plugin)` helper is retained as-is.

---

## Phase CT-1 — `ControllerRegistry` 🔲

**New file:** `packages/pymodaq/src/pymodaq/control_modules/controller_registry.py`

See `CONTROLLER_THREAD_PLAN.md` Phase 1 for full spec.

Key points:
- Maps `ControllerKey(plugin_class, controller_id)` → `(ControllerThread, Parameter)`
- Creates shared `Parameter` model in GUI thread before hardware thread starts
- Ref-counted: `acquire()` / `release()`, torn down at zero
- Injectable for test isolation (`ControllerRegistry.get()` for production,
  `ControllerRegistry()` for tests)

**Deliverable**: registry + unit tests (no GUI, no hardware).

---

## Phase CT-2 — `ControllerThread` + `ChannelScheduler` 🔲

**New file:** `packages/pymodaq/src/pymodaq/control_modules/controller_thread.py`

Replaces `hardware_worker.py`. See `CONTROLLER_THREAD_PLAN.md` Phase 2 for
full spec.

Key points:
- One `QThread` per physical controller (not per GUI module)
- Owns plugin instance + SDK object
- `ChannelScheduler` is a child `QObject` (follows `moveToThread` automatically)
- Fully async: all acquisition via `request_read` / `request_write` slots,
  results via `data_ready` / `change_done` signals
- Old-style adapters: `grab_data` fire-and-forget connected to `data_ready`;
  `move_abs` + polling timer → `change_done`
- `settings_changed(path, data, change)` signal posts parameter updates to GUI
  thread (never calls `Parameter.setValue()` directly)
- `hardware_status(connected, info)` signal for disconnect/reconnect

**Deliverable**: `ControllerThread` + `ChannelScheduler` + integration tests
with mock plugin (headless).

---

## Phase CT-3a — DAQ_Move / DAQ_Viewer as thin subscribers 🔲

**Modified files:** `daq_move.py`, `daq_viewer.py`, `utils.py`

See `CONTROLLER_THREAD_PLAN.md` Phase 3a for full spec.

Key points:
- Each DAQ module calls `ControllerRegistry.acquire()`, gets back
  `(ControllerThread, shared_parameter)`
- Connects channel slots / signal filters
- `move_done_signal` re-emitted from `change_done` filtered by channel name
  (DAQ_Scan sees no change)
- `_on_capabilities_updated` in compact dock wired from
  `ControllerThread.capabilities_signal` (not from per-module relay)
- `ActuatorWorker` / `DetectorWorker` stop owning a `QThread`; become thin
  stubs or are removed

**Deliverable**: refactored `DAQ_Move` + `DAQ_Viewer`; full test suite passes.

---

## Phase CT-3b — `HardwareWidget` 🔲

**New file:** `packages/pymodaq/src/pymodaq/control_modules/hardware_widget.py`

See `CONTROLLER_THREAD_PLAN.md` Phase 3b for full spec.

Key points:
- One per `ControllerThread` / physical controller
- Owns shared `Parameter` model (GUI thread)
- Exposes shared `QAction`s ("Settings", "Init HW") added to all child DAQ
  toolbars — Qt's native `QAction` sharing propagates enabled/checked state
- Coloured status indicator consistent across all child DAQ docks
- `widget_sync` useful for other cross-DAQ UI state (all in GUI thread)

**Deliverable**: `HardwareWidget`; reduced per-DAQ toolbar clutter.

---

## Phase 3.5 — Preset serialization of capability selection 🔲

**Pending**: Phase CT-3a.

**New file:** `capability_selection.py`
**Modified files:** `preset_manager.py`, `dashboard.py`

### Design

The preset records which declared capabilities are **deselected** (the default
is all-selected). Confirmed post-`ini` capabilities are not persisted — they are
re-discovered via `capabilities_updated_signal`.

```xml
<capability_selection default="all">
  <deselect name="histogram"/>
  <expose param_path="settings/binning" as="variable" display_name="Binning"/>
</capability_selection>
```

### Tasks

- [ ] `CapabilitySelection` dataclass: `deselected: frozenset[str]`,
  `exposed_params: list[ExposedParam]`; `to_xml()` / `from_xml()`; `is_selected(name)`
- [ ] `PresetManager`: `save_capability_selection` / `load_capability_selection`
- [ ] Dashboard uses `CapabilitySelection` when building `ChannelControl` rows:
  skips deselected names, recreates exposed-param capabilities
- [ ] Compact dock deselect action: `stop_grab` → remove row

---

## Phase 4 — Dynamic capabilities from parameter tree 🔲

**Pending**: Phase 3.5.

**New file:** `param_to_capability.py`
**Modified files:** `pymodaq_gui/parameter/` (right-click context menu — cross-package PR)

### Tasks

- [ ] `param_to_capability(param) -> Observable | Variable`:
  - `float`/`int` → `ContinuousVariable` (lo/hi from limits)
  - `list` → `DiscreteVariable` (choices from values)
  - `bool` → `Variable` (dtype `'bool'`)
  - other → `Observable`
- [ ] Right-click menu on parameter tree nodes: "Expose as Observable/Variable"
  → calls `param_to_capability`, appends to plugin `capabilities`, emits
  `capabilities_updated_signal`
- [ ] `ControllerThread` relays `capabilities_updated_signal` to all subscribers
  (already the case from CT-2); compact dock diff logic handles new rows
  automatically

---

## Phase 5 — `DAQ_Monitor` 🔲

**Pending**: Phase CT-3a.

**New file:** `daq_monitor.py`

### Tasks

- [ ] `DAQ_Monitor(CustomApp)` — dockable display panel:
  - Channel list: one checkbox per `Observable` / `Variable` across all loaded
    controllers
  - On check: open viewer sized by `capability.shape` / `capability.dtype`
    (scalar → Viewer0D, 1-D → Viewer1D, 2-D → Viewer2D); subscribe to
    `ControllerThread.data_ready` filtered by channel name
  - On uncheck: close viewer, unsubscribe from `data_ready`
- [ ] Old-style plugin fallback: translate `dte_signal` → `data_ready` via
  compatibility adapter; no legacy path removed until deprecation window closes
- [ ] Dashboard wiring: `ModulesManager` registers / unregisters plugin
  capabilities with `DAQ_Monitor` on load / unload

---

## Migration guarantee (Option B)

| Phase | Old plugins | New plugins |
|-------|-------------|-------------|
| 0–2 | Unaffected; all old abstract methods still work | Can use `ChannelControl` + `query_data`/`change_to` |
| CT-1/2 | Routed through old-style adapters in `ControllerThread` | `query_data`/`change_to` called directly |
| CT-3a | `move_done_signal` / `grab_done_signal` preserved in DAQ_Move/Viewer | Same signals, same scan engine compat |
| 3.5 | Preset with no `<capability_selection>` → all-selected default | Deselected caps persisted |
| 4–5 | New UI features available but not required | Full dynamic capabilities |

**Rule**: every PR must run the full existing test suite without new failures.
New tests are added in the same PR as the feature they cover.

---

## Implementation order (agreed)

1. **Phase 0** — naming aliases + plan docs (trivial, this PR)
2. **Phase CT-1** — `ControllerRegistry` (no GUI, pure Python)
3. **Phase CT-2** — `ControllerThread` + `ChannelScheduler` (cornerstone)
4. Rebuild Phases 0–2 capabilities work on new branch (ChannelControl, compact
   dock, DAQ_Plugin_base — clean history)
5. **Phase CT-3a** — thin subscribers
6. **Phase CT-3b** — `HardwareWidget`
7. **Phase 3.5 → 5** — preset, dynamic caps, DAQ_Monitor
