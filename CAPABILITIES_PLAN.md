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
  interrupt still works.  The polling fallback *also emits* `change_done_signal`
  when it resolves, so `DAQ_HardwareWorker` (Phase 3) can treat all plugins
  uniformly.
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

The plugin emits **`capabilities_updated_signal(new_caps: Capabilities)`**
whenever capabilities change.  The framework responds at two levels:

- **In-place refinement** (`ChannelControl.update_capability(new_cap)`) — same
  channel exists, metadata changed.  Updates spinbox bounds
  (`ContinuousVariable` lo/hi), repopulates combobox items (`DiscreteVariable`
  choices).  `Observable` shape changes are forwarded to `DAQ_Monitor` only
  (toolbar is unaffected).
- **Structural diff** — `capabilities_updated_signal` triggers a diff of old vs
  new `Capabilities`; new channels get new `ChannelControl` rows added to the
  compact dock, removed channels get their rows cleaned up.  The diff lives in
  `ModuleCompactDock` (Phase 1).

### Selection and acquisition are separate concerns

**Selected** means a `ChannelControl` row exists for that capability and is
subscribed to the worker's data signal.  That is all — no hardware activity
occurs from selection alone.

**Acquisition** is event-driven, not polled:

| User action | Worker behaviour |
|-------------|-----------------|
| Snap | one-shot `query_data([name], fresh=True)`, result delivered to row |
| Grab | loop calling `query_data([name], fresh=True)` at rate until Stop |
| Stop | exit grab loop for that channel |
| Readback display (e.g. actuator spinbox) | `query_data([name], fresh=False)` — returns last cached value, no hardware call |

`DAQ_HardwareWorker` tracks `grabbed_names: set[str]` — the channels
currently in a continuous grab loop.  Outside of an active grab, the worker is
idle for that channel.  A ChannelControl that is selected but not grabbing
causes zero hardware traffic.

The `fresh: bool` argument is added to `query_data` throughout:
- `fresh=True` — read from hardware (snap / grab tick)
- `fresh=False` — return last cached value (position readback, status display)

Default at load time: **all declared capabilities are selected** (rows
created).  The user deselects individual channels; deselection is what gets
persisted in the preset.

Preset storage saves **declared (class-level) capabilities** and the
**deselected set** so the dashboard can reconstruct the full UI layout without
hardware connected.  Confirmed capabilities (post-`ini`) are **not** persisted
— they are re-discovered on next hardware init and delivered via
`capabilities_updated_signal`.

---

## Phase 0 — `ChannelControl` dataclass  ✅ COMPLETE

**New file:** `packages/pymodaq/src/pymodaq/control_modules/channel_control.py`

### Tasks

- [x] Define `ChannelControl` dataclass:
  - `capability: Observable | Variable`
  - `query: Callable[[bool], DataToExport]` — `fresh=True` reads hardware,
    `fresh=False` returns last cached value; snap/grab pass `True`, readback
    display passes `False`
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

> **Deferred to Phase 1:** `ChannelControl.update_capability(new_cap)` — in-place
> metadata refresh.  Kept out of Phase 0 because it requires the dock wiring to
> be meaningful.

### Tests

- `packages/pymodaq/tests/control_modules/test_capabilities.py` — 55 tests (restored from git)
- `packages/pymodaq/tests/control_modules/test_channel_control.py` — 72 passed, 16 skipped (Qt)

---

## Phase 1 — Capabilities-driven compact dock  ✅ COMPLETE
**Modified files:**
- `packages/pymodaq/src/pymodaq/utils/compact_dock_manager.py`
- `packages/pymodaq/src/pymodaq/control_modules/channel_control.py`
  (add `set_locked`; `update_capability` already exists from Phase 0)

### Design decisions (resolved before coding)

#### D1 — Separate storage: `_RowData` gains a `channel_control` field

`_RowData` gets a second optional field:

```python
@dataclass
class _RowData:
    toolbar: QtWidgets.QWidget
    module: object = None           # DAQ_Move | DAQ_Viewer — legacy rows only
    channel_control: object = None  # ChannelControl — new-style rows only
```

`module` and `channel_control` are mutually exclusive: exactly one is non-None per row.
`add_module()` sets `module`; `add_channel()` sets `channel_control`.

A new `channel_controls` property mirrors the existing `modules` property:

```python
@property
def channel_controls(self):
    return [r.channel_control for r in self._rows.values()
            if r.channel_control is not None]
```

`_apply_to_modules` continues iterating `self.modules` (legacy rows only —
`ChannelControl` rows have no `module.ui` interface).

#### D2 — Lock: `ChannelControl.set_locked(locked: bool)` (add to `channel_control.py`)

`_apply_lock` currently calls `module.ui.has_action(name)` for each name in
`LOCKABLE_ACTIONS`.  `ChannelControl` has no `.ui`, and its button `objectName`s
(`'go_btn'`, `'snap_btn'`, etc.) don't match `LOCKABLE_ACTIONS` entries.

Resolution — add to `ChannelControl`:

```python
_LOCKABLE_OBJECT_NAMES = frozenset({
    'go_btn', 'set_btn', 'toggle_btn',
    'snap_btn', 'grab_btn', 'stop_btn',
    'value_spin', 'choices_combo',
})

def set_locked(self, locked: bool) -> None:
    """Enable/disable all interactive widgets in the toolbar."""
    if self.toolbar is None:
        return
    from qtpy.QtWidgets import QWidget
    for widget in self.toolbar.findChildren(QWidget):
        if widget.objectName() in _LOCKABLE_OBJECT_NAMES:
            widget.setEnabled(not locked)
```

`_apply_lock` in `ModuleCompactDock` gains a second loop after the legacy one:

```python
def _apply_lock(self, locked: bool):
    # legacy modules
    for module in self.modules:
        for name in LOCKABLE_ACTIONS:
            if not module.ui.has_action(name):
                continue
            module.ui.set_action_enabled(name, not locked)
            widget = getattr(module.ui.get_action(name), 'widget', None)
            if widget is not None:
                widget.setEnabled(not locked)
    # new-style channel controls
    for cc in self.channel_controls:
        cc.set_locked(locked)
```

This keeps the two row types cleanly separated; no "duck-type on `.toolbar`"
ambiguity.

#### D3 — Alignment: `ChannelControl` rows do NOT participate

Cross-row alignment (`_update_alignment`) is a legacy-module concern: it aligns
name labels and plugin-selector combos across `DAQ_Move` / `DAQ_Viewer` rows by
fixing their pixel widths.  `ChannelControl` toolbars have their own natural
sizing (the `QLabel` with the channel name uses `sizeHint()`).  The two row
types are not expected to share columns.

`_update_alignment` is unchanged; it iterates `self.modules` only.

#### D4 — Name→row index: `self._channel_rows: dict[str, ChannelControl]`

`_on_capabilities_updated` must look up existing rows by channel name.  Add to
`ModuleCompactDock.__init__`:

```python
self._channel_rows: dict[str, 'ChannelControl'] = {}
```

`add_channel(cc)` inserts `self._channel_rows[cc.capability.name] = cc`.
`remove_channel(name)` removes the entry and calls `remove_widget` on the toolbar.

#### D5 — Signal wiring deferred to Phase 2

`_on_capabilities_updated` is **defined** here (Phase 1) but **not wired**.
`capabilities_updated_signal` does not exist until `DAQ_Plugin_base` is added in
Phase 2.  The `.connect(...)` call belongs in Phase 2 (or wherever the plugin is
loaded into the dock manager).  Phase 1 tests call `_on_capabilities_updated`
directly.

#### D6 — Thread safety: `QueuedConnection` (mandatory, enforced in Phase 2)

`capabilities_updated_signal` can fire from a hardware thread (post-`ini()`
confirmed capabilities, post-`commit_settings()` parameter changes).  When the
connection is made (Phase 2), it **must** use `Qt.QueuedConnection` so the slot
runs in the GUI thread:

```python
plugin.capabilities_updated_signal.connect(
    dock._on_capabilities_updated,
    Qt.ConnectionType.QueuedConnection,
)
```

Document this requirement here so Phase 2 implementors don't miss it.

---

### Tasks

- [x] **`_RowData`** — add `channel_control: object = None` field (D1); keep
  `module` for legacy rows only.
- [x] **`ModuleCompactDock`** — add `channel_controls` property (D1).
- [x] **`ChannelControl.set_locked(locked)`** — new method in
  `channel_control.py`; finds interactive widgets by `objectName` and
  enables/disables them (D2).  Add `_LOCKABLE_OBJECT_NAMES` frozenset constant.
- [x] **`_apply_lock`** — add second loop over `self.channel_controls` calling
  `cc.set_locked(locked)` (D2).
- [x] **`ModuleCompactDock.add_channel(channel_control)`** — calls base
  `add_widget(cc.toolbar, create_toolbar=False, ...)` and stores in
  `_channel_rows` (D4).  `ActuatorCompactDock` and `DetectorCompactDock`
  override to validate capability kind (Variable vs Observable).
- [x] **`ModuleCompactDock.remove_channel(name)`** — looks up
  `_channel_rows[name]`, calls `remove_widget(cc.toolbar)`, removes from
  `_channel_rows` (D4).
- [x] **`ModuleCompactDock._channel_rows`** — `dict[str, ChannelControl]`
  initialised in `__init__` (D4).
- [x] **`ModuleCompactDock._on_capabilities_updated(new_caps: Capabilities)`**
  — implement diff; **not wired** (D5).  Stubs query/change as None for new
  channels; Phase 3 wires real callables.
- [x] **`update_capability` already implemented** — wired via
  `_on_capabilities_updated`.
- [x] **Alignment unchanged** — `_update_alignment` / `_get_module_align_widgets`
  iterate `self.modules` only; no changes needed (D3).

### Tests to update / add

`packages/pymodaq/tests/utils/compact_dock_manager_test.py` (update existing)

- Existing `add_module` tests must still pass unchanged
- Add: `add_channel` with `ContinuousVariable` → row appears in actuator dock;
  `_channel_rows` contains the entry
- Add: `add_channel` with `Observable` → row appears in detector dock
- Add: `set_locked(True)` on a `ContinuousVariable` `ChannelControl` disables
  `'go_btn'` and `'value_spin'`; `set_locked(False)` re-enables them
- Add: `_apply_lock` disables `ChannelControl` rows via `set_locked` and legacy
  module rows via `module.ui.set_action_enabled` — both in the same dock
- Add: mixed dock (legacy module row + `ChannelControl` row) coexist; `modules`
  returns only the legacy module, `channel_controls` returns only the CC
- Add: `update_capability` (called directly) updates spinbox bounds without
  removing the row
- Add: `_on_capabilities_updated` with new capability name → new row added,
  `_channel_rows` updated
- Add: `_on_capabilities_updated` with dropped capability name → row removed,
  `_channel_rows` entry deleted
- Add: `_on_capabilities_updated` with same name, changed `lo`/`hi` → in-place
  spinbox update (no row removal)
- Add: `remove_channel(name)` removes the row; `_channel_rows` no longer
  contains the entry; dock row count decremented

---

## Phase 2 — New plugin base class ✅ COMPLETE

**New file:** `packages/pymodaq/src/pymodaq/control_modules/plugin_base.py`

**Modified files:** `move_utility_classes.py`, `viewer_utility_classes.py`

### Tasks

- [x] Define `DAQ_Plugin_base` in `plugin_base.py`:
  - Stubs: `query_data(names=None)`, `change_to(name, value)` (raise NotImplementedError)
  - Class attribute: `_new_style_plugin: ClassVar[bool] = True`
  - Signals: `change_done_signal = Signal(str, object)`, `capabilities_updated_signal = Signal(object)`
  - Default polling fallback: `_poll_until_done(name, target, epsilon, timeout, poll_interval)`
  - `capabilities` property (lazy infer + cache) with setter that emits signal
- [x] `DAQ_Move_base(DAQ_Plugin_base)` — adapter methods:
  - `query_data()` wraps `get_actuator_value()` → `DataToExport`
  - `change_to(name, value)` delegates to `move_abs(value)`
- [x] `DAQ_Viewer_base(DAQ_Plugin_base)` — adapter stub:
  - `query_data()` delegates to `parent.snap()` when in hardware thread
- [x] **Signal relay chain wired** (all `QueuedConnection`):
  - `DAQ_Move_Hardware`: `capabilities_updated_signal` added; wired from plugin in `ini_stage`
  - `DAQ_Move`: `capabilities_updated_signal` added; wired from hardware in thread setup
  - `DAQ_Detector`: `capabilities_updated_signal` added; wired from plugin in `ini_detector`
  - `DAQ_Viewer`: `capabilities_updated_signal` added; wired from hardware in thread setup
  - `dashboard.py`: wires `DAQ_Move.capabilities_updated_signal` → compact actuator dock;
    and `DAQ_Viewer.capabilities_updated_signal` → compact detector dock
- [x] Tests: `test_plugin_base.py` (new) — signals, flag, property setter/emit, stubs, poll_until_done

Old abstract methods (`ini_stage`, `grab_data`, `move_abs`, `get_actuator_value`,
…) remain and still work — no existing plugin is broken.

### Tests to update / add

`packages/pymodaq/tests/control_modules/test_plugin_base.py` (new)

- `_poll_until_done` terminates when within epsilon, times out correctly
- `_poll_until_done` emits `change_done_signal` on resolution
- `capabilities_updated_signal` emitted when `capabilities` property is set
- `DAQ_Move_base` adapter: calling `move_abs` on a new-style plugin that
  implements `change_to` works end-to-end
- `DAQ_Viewer_base` adapter: calling `grab_data` on a new-style plugin that
  implements `query_data` works end-to-end
- `capabilities_updated_signal` connected with `QueuedConnection` (verify
  connection type in wiring test)

`packages/pymodaq/tests/control_modules/test_move_utility_classes.py` (update)

- Existing tests still pass; no regressions from adapter addition

`packages/pymodaq/tests/control_modules/test_viewer_utility_classes.py` (update)

- Same: no regressions

---

## Phase 3 — Framework detection and unified hardware worker  ✅ COMPLETE

**Modified files:** `daq_move.py`, `daq_viewer.py`, `move_utility_classes.py`,
`viewer_utility_classes.py`, `utils.py`

**New file:** `packages/pymodaq/src/pymodaq/control_modules/hardware_worker.py`

### Tasks

- [x] `_is_new_style(plugin) -> bool`:
  - Returns `getattr(plugin, '_new_style_plugin', False)` — checks the class
    attribute set in Phase 2; avoids MRO inspection
- [x] `DAQ_HardwareWorker(QObject)` — one instance **per plugin**, owned by the
  `DAQ_Move` / `DAQ_Viewer` that loaded it; torn down in `close()`:
  - Demand-driven, not a polling loop.  Hardware is only called when a
    `ChannelControl` explicitly requests it.
  - `snap(name: str)` — one-shot `query_data([name], fresh=True)`; result
    emitted on `data_ready_signal` and cached.
  - `grab(name: str)` — start a per-channel loop: repeatedly calls
    `query_data([name], fresh=True)` at configured rate, emitting each
    result on `data_ready_signal` and updating cache.
  - `stop(name: str)` — exit the grab loop for that channel.
  - `get_cached(name: str) -> DataToExport` — returns last result without
    touching hardware (`fresh=False` path); used by readback displays.
  - `grabbed_names: set[str]` — channels currently in an active grab loop;
    empty means zero hardware traffic.
  - Serialises all hardware access: snap and grab requests for different
    channels are queued and executed one at a time on the worker thread,
    preventing concurrent plugin calls.
  - `change_to(name, value)` — queued write; emits `change_done_signal`
    when complete (native or via polling fallback).
  - Emits `data_ready_signal(str, DataToExport)` (channel name + data) →
    each `ChannelControl` filters by its own name; `DAQ_Monitor` (Phase 5)
    consumes all.  Signal exists from Phase 3 but `DAQ_Monitor` connection
    is added in Phase 5.
- [x] `DAQ_Move_Hardware.queue_command` — branch:
  - old-style (`_is_new_style` → False) → existing path unchanged
  - new-style → `DAQ_HardwareWorker`
- [x] `DAQ_Detector.queue_command` — same branch
- [x] `DAQ_Move_base._new_style_plugin = False` — marks adapter as old-style
- [x] `DAQ_Viewer_base._new_style_plugin = False` — same
- [x] `_connect_capabilities_signal` — connects unconditionally (all plugins have
  the signal via `DAQ_Plugin_base`)

### Tests to update / add

`packages/pymodaq/tests/control_modules/test_hardware_worker.py` (new)

- `snap(name)` triggers exactly one `query_data` call and emits `data_ready_signal`
- `grab(name)` loops at configured rate, emits `data_ready_signal` each tick
- `stop(name)` halts the grab loop; no further `query_data` calls issued
- `get_cached(name)` returns last value without calling `query_data`
- Snap and grab requests for two different channels are serialised (not concurrent)
- `change_to` queued correctly; `change_done_signal` relayed
- Worker torn down cleanly on `close()` — no dangling thread, grab loops exit
- Old-style plugin routed through old code path (no regression)

`packages/pymodaq/tests/control_modules/test_daq_move.py` (update)

- New-style plugin goes through `DAQ_HardwareWorker`, not `DAQ_Move_Hardware`
- Old-style plugin still works via `DAQ_Move_Hardware`

`packages/pymodaq/tests/control_modules/test_daq_viewer.py` (update)

- Same pattern as above for `DAQ_Detector`

---

## Phase 3.5 — Preset serialization of capabilities

**Modified files:** `pymodaq/preset_manager.py` (or wherever preset XML is
written/read), `pymodaq/dashboard.py`

**New file:**
`packages/pymodaq/src/pymodaq/control_modules/capability_selection.py`

### Design

The existing preset records which instruments to load and their full parameter
trees.  The new section records **which capabilities the user has deselected**
plus any **parameter-tree exposures** the user created.

#### Selection model

| Kind | Default | How stored |
|------|---------|-----------|
| Declared capabilities (class-level `Observable` / `Variable`) | **All selected** — row exists, worker queries it | Only *deselected* names stored; new capabilities auto-appear selected |
| Exposed parameters (Phase 4 dynamic exposure) | None selected | *Explicit list* — user opts in per parameter path |

A preset with no `<capability_selection>` block is identical to one where every
declared capability is selected — safe default for existing workflows.

Deselected = no row in compact dock AND not in `watched_names` — the worker
never calls `query_data` for that channel.

#### XML format (added inside each instrument's existing preset block)

```xml
<capability_selection default="all">
  <!-- declared caps: only list what is explicitly deselected -->
  <deselect name="histogram"/>
  <deselect name="roi_info"/>

  <!-- exposed params (Phase 4): must be explicit, never implicit -->
  <expose param_path="settings/binning"     as="variable" display_name="binning"/>
  <expose param_path="settings/exposure_ms" as="variable" display_name="exposure_ms"/>
</capability_selection>
```

`default="all"` is the only supported value for now; reserved for a future
`default="none"` opt-in mode for plugins with many channels.

#### What is NOT persisted

- **Confirmed capabilities** (post-`ini` shape refinement from hardware): these
  are re-discovered on next `ini()` via `capabilities_updated_signal`.
- **Viewer layout** inside `DAQ_Monitor`: treated as session state, not preset
  state (separate save/restore if needed in Phase 5).

### Tasks

- [ ] `CapabilitySelection` dataclass:
  - `deselected: frozenset[str]` — names of declared capabilities that are
    off; worker will not query them, no row rendered
  - `exposed_params: list[ExposedParam]` — each has `param_path: str`,
    `as_kind: Literal['observable', 'variable']`, `display_name: str`
  - `to_xml() -> Element`
  - `from_xml(element) -> CapabilitySelection` (classmethod); missing element →
    `CapabilitySelection()` (all declared selected, no exposed params)
  - `is_selected(name: str) -> bool` — convenience; returns `name not in self.deselected`
- [ ] `PresetManager` extended:
  - `save_capability_selection(instrument_name, selection)` — writes
    `<capability_selection>` block into instrument's preset entry
  - `load_capability_selection(instrument_name) -> CapabilitySelection`
- [ ] Dashboard / `ModulesManager` uses `CapabilitySelection` when building
  `ChannelControl` rows at load time:
  - Skip deselected declared capabilities (no row, no `add_channel()` call,
    no subscription — worker will never be asked to query that channel)
  - Recreate exposed-param capabilities (via `param_to_capability`, Phase 4)
    and add their rows
- [ ] Compact dock deselect action (toggle off a row):
  - If channel is currently grabbing, call `worker.stop(name)` first
  - Remove the row and its subscription from the dock

### Tests to add

`packages/pymodaq/tests/control_modules/test_capability_selection.py` (new)

- Round-trip `CapabilitySelection → XML → CapabilitySelection` preserves all fields
- Missing XML element → empty selection (all-selected default)
- `is_selected` returns False for deselected names, True otherwise
- Deselected name excluded when building `ChannelControl` list
- `exposed_params` round-trips with all three `as_kind` values

---

## Phase 4 — Dynamic capabilities from parameter tree

**New file:** `packages/pymodaq/src/pymodaq/control_modules/param_to_capability.py`

**Modified files:**
- `pymodaq_gui/parameter/` — right-click context menu on parameter tree nodes
  (**cross-package change**: `pymodaq_gui` is a lower-level package; the menu
  addition must land in a `pymodaq_gui` PR before or alongside this phase)
- `move_utility_classes.py`, `viewer_utility_classes.py` — connect menu action
  to `capabilities_updated_signal`

### Tasks

- [ ] `param_to_capability(param) -> Observable | Variable`:
  - `float` / `int` param → `ContinuousVariable`; reads `limits` for `lo`/`hi`
  - `list` param → `DiscreteVariable`; reads `values` for `choices`
  - `bool` param → `Variable` (dtype `'bool'`)
  - anything else → `Observable`
- [ ] Right-click context menu on parameter tree nodes (`pymodaq_gui`):
  - "Expose as Observable" / "Expose as Variable"
  - Calls `param_to_capability`, appends to `plugin.capabilities`
  - Emits **`capabilities_updated_signal`** on plugin (consistent name)
- [ ] Dashboard / compact dock manager listens to `capabilities_updated_signal`
  → creates new `ChannelControl` → calls `add_channel()` on the right dock
  (diff logic already in place from Phase 1)

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
- [ ] **Old-style plugin fallback**: for plugins that go through the legacy
  `DAQ_Move_Hardware` / `DAQ_Detector` path (not `DAQ_HardwareWorker`), keep
  the inline viewer management currently inside `DAQ_Viewer` intact and wire it
  to `DAQ_Monitor`'s channel list via a compatibility adapter that translates
  `dte_signal` into `data_ready_signal`.  Do not remove legacy path until
  deprecation window closes.
- [ ] Dashboard wiring: `ModulesManager` registers plugin capabilities with
  `DAQ_Monitor` on load/unload

### Tests to add

`packages/pymodaq/tests/control_modules/test_daq_monitor.py` (new)

- Channel list populated from capabilities
- Viewer opened/closed on check/uncheck
- Correct viewer type chosen by shape
- Data fed from mock `data_ready_signal`
- Old-style plugin data (via `dte_signal` adapter) appears in channel list

---

## Migration guarantee (Option B — throughout all phases)

| Phase | Old plugins | New plugins |
|-------|-------------|-------------|
| 0–1   | Unaffected; compact dock still accepts legacy `add_module()` | Can use `ChannelControl` directly |
| 2     | Old abstract methods work; `DeprecationWarning` added | Implement `query_data`/`change_to` only; set `_new_style_plugin = True` |
| 3     | Routed through existing `DAQ_Move_Hardware`/`DAQ_Detector` | Routed through `DAQ_HardwareWorker` |
| 3.5   | Preset with no `<capability_selection>` → all-selected default | Preset records deselected caps + exposed params; deselected = no row, no subscription, never queried |
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
