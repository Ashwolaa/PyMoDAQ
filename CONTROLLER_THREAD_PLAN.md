# ControllerThread Architecture Plan

**Goal**: move PyMoDAQ from "one hardware thread per GUI module" to "one hardware
thread per physical controller, with multiple lightweight GUI subscribers".

This removes the master/slave race condition, simplifies new-plugin authoring, and
makes it possible to attach arbitrary numbers of GUI frontends (DAQ_Move,
DAQ_Viewer, scan engines, dashboards) to the same instrument without conflict.

---

## Implementation status

| Phase | Status |
|---|---|
| 0 — Naming aliases | ✅ Complete (`ActuatorPlugin`, `DetectorPlugin`, `PluginBase` aliases present) |
| 1 — ControllerRegistry | ✅ Complete |
| 2 — ControllerThread | ✅ Complete (role-based dispatch for combined plugins — see Phase 2 notes) |
| 3a — DAQ_Move / DAQ_Viewer wiring | ✅ Complete |
| 3b — HardwareWidget | ✅ Complete (shared HardwarePanel per key; group_snapshot dialog deferred) |
| 4 — Old-style adapter hardening | ✅ Complete (multi-axis `axis_name`, `hardware_averaging`, SDK-callback thread all tested in `test_controller_thread.py` + `test_multi_subscriber_integration.py`; combined plugin dispatch tested in `TestCombinedPlugin`) |
| 5 — Deprecate master/slave param tree | ✅ Complete (deprecation cycle in progress — see Phase 5 notes) |

---

## Current architecture (baseline)

```
DAQ_Move_1 (GUI thread)        DAQ_Move_2 (GUI thread)
     │ QThread_1                    │ QThread_2
     ▼                              ▼
ActuatorWorker_1               ActuatorWorker_2
     │ plugin_1.controller ──────── plugin_2.controller
     │        ↑ same SDK object, no lock ↑
     ▼                              ▼
SDK / hardware
```

Key problems:
- One QThread per GUI module regardless of shared hardware.
- Master/slave is a raw Python object reference — no mutex, no queue.
- Cross-module conflicts are still possible.
- Plugin authors must understand Qt threading.

---

## Target architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  GUI thread                                                      │
│                                                                  │
│  DAQ_Move_X   DAQ_Move_Y   DAQ_Viewer_1                          │
│    own: main_settings (name, ui type)                            │
│    own: per-channel params (axis selection, units, epsilon)      │
│    own: toolbar actions (move/grab/stop)                         │
│    share: hw_settings Parameter (via _hw_settings ref)           │
│    share: hardware_status signal display                         │
│    │  ↕ queued signals only                                      │
└────┼─────────────────────────────────────────────────────────────┘
     │
┌────▼─────────────────────────────────────────────────────────────┐
│  ControllerThread  (one QThread per physical controller)         │
│                                                                  │
│  owns: plugin instance(s) + SDK object                           │
│  owns: _ReadGroup instances (one QTimer per named group)         │
│  holds: read-only ref to shared hw_settings Parameter            │
│                                                                  │
│  Signals → GUI thread (queued):                                  │
│    data_ready(channel, DataToExport, is_temp)                    │
│    change_done(channel, DataActuator)                            │
│    hardware_status(connected: bool, info: str)                   │
│    status_message(str)                                           │
│    settings_changed(channel, path, data, change)                 │
│    capabilities_signal(Capabilities)                             │
│                                                                  │
│  Slots ← GUI thread (queued):                                    │
│    ini_hardware()                                                │
│    close_hardware()                                              │
│    request_read(channel)                                         │
│    request_snap(channel, Naverage)                               │
│    request_write(channel, value | ControlCommand)                │
│    start_grab(channel, period_ms, group='')                      │
│    stop_grab(channel)                                            │
│    update_settings(path, data, change)                           │
└──────────────────────────────────────────────────────────────────┘
```

**Key ownership rules**:
- `hw_settings` Parameter lives in the GUI thread, created by `ControllerRegistry`
  before the hardware thread starts. `ControllerThread` holds a read-only reference
  used only at `ini_hardware` time. All subsequent plugin→GUI writes go through
  `settings_changed` (queued signal).
- `main_settings` (module name, UI type, refresh rate) stays owned by each
  `DAQ_Move` / `DAQ_Viewer` individually — not shared.
- Per-channel parameters (axis selection, units, epsilon) live in each module's
  local settings (`_PER_CHANNEL_PARAMS`), not in `hw_settings`. They are never
  mirrored to the shared tree.
- Plugin instance and SDK object live exclusively in `ControllerThread`'s thread.

Master/slave disappears — replaced by channel subscription.

---

## Phase 0 — Naming cleanup

Add aliases; keep old names as deprecated stubs:

```python
# plugin_base.py
PluginBase = DAQ_Plugin_base

# move_utility_classes.py
ActuatorPlugin = DAQ_Move_base

# viewer_utility_classes.py
DetectorPlugin = DAQ_Viewer_base
```

**Risk**: zero.

---

## Phase 1 — ControllerRegistry ✅

Process-global singleton mapping `ControllerKey` → live `ControllerThread`.
The shared `hw_settings` Parameter is created here, in the GUI thread, before the
hardware thread starts.

```python
@dataclass(frozen=True)
class ControllerKey:
    hardware_class: type   # shared driver class; falls back to plugin class
    controller_id: int     # user-assigned grouping integer (0–9999)

class ControllerRegistry:
    @classmethod
    def get(cls) -> ControllerRegistry: ...   # module-level singleton

    def attach(
        self,
        key: ControllerKey,
        plugin_class: type,
        params_state: dict | None = None,
        subscriber: object | None = None,
    ) -> tuple[ControllerThread, Parameter]: ...

    def detach(self, key: ControllerKey, subscriber: object | None = None) -> None: ...
    def close_all(self) -> None: ...
```

**Note**: public API uses `attach`/`detach` (not `acquire`/`release` as in earlier
drafts).

Override points `_make_settings()` and `_make_thread()` allow test injection
without a running Qt event loop.

---

## Phase 2 — ControllerThread ✅

### Grab-timer model: named read groups

The central design insight is that physical controllers often read ALL channels in
one hardware transaction (e.g. a multi-axis stage returning X/Y/Z positions at
once). Splitting polling into one timer per channel would issue N redundant reads.

**Data structures**:

```python
@dataclass
class _ChannelState:
    sub_count: int = 0
    period_ms: float = 0.0   # minimum requested across all subscribers

    def subscribe(self, period_ms) -> None: ...
    def unsubscribe(self) -> bool: ...   # True = last subscriber left

@dataclass
class _ReadGroup:
    channels: dict[str, _ChannelState]
    timer: QTimer | None = None
    # grab serialisation is via CT-level _grab_in_flight, not per-group

# CT instance state:
_groups: dict[str, _ReadGroup]  # named groups; '' = default
_solo: dict[str, tuple[_ChannelState, QTimer]]  # group=None channels
_grab_in_flight: bool           # one grab_data() at a time (all modes)
_pending_group: str | None      # which group triggered current grab
_pending_channel: str           # channel for snap / solo grabs
```

**`start_grab(channel, period_ms, group='')`**:

| `group` value | Behaviour |
|---|---|
| `''` (default) | Joins the default shared group; one hardware read fans out to all. Correct for multi-axis controllers that return all positions in one SDK call. |
| Any other string | Independent group with its own `QTimer`. Use `group='detector'` / `group='actuator'` for combined instruments (actuator polling must not block a slow camera grab). |
| `None` | Solo: fully independent `QTimer` per channel, completely decoupled. |

**Rate policy**: fastest-subscriber-wins — effective period = min over all
subscribers on that channel. Conservative: rate does not go back up when the
fastest subscriber leaves (slightly-too-fast timer is harmless; subscribers
already filter by channel name).

**Grab serialisation**: `_grab_in_flight` is a CT-level global flag. Only one
`grab_data()` call can be outstanding at a time per plugin instance (all modes:
group timers, solo timers, snaps). `_pending_group` records which named group
triggered the current grab so `_on_detector_data_ready` fans out the DTE to the
right channels.

**Thread safety for SDK callbacks**: Qt's `AutoConnection` (default) checks the
receiver's thread affinity at emit time. The plugin is a QObject created inside
`ini_hardware()` (which runs in the hardware thread), giving it the hardware
thread affinity. If an SDK callback fires from a C extension thread and emits
`dte_signal`, Qt automatically uses `QueuedConnection` — safe by construction,
no explicit connection type needed.

**Old-style plugin support**: `_PluginParentShim` satisfies `self.parent.title`
and `self.parent.status_sig.emit()` without the full Worker hierarchy. The shim
forwards `ThreadCommand` payloads to `status_message`, `data_ready`, or
`settings_changed` as appropriate.

**Combined plugin role-based dispatch**: `_on_group_tick` and `_solo_tick`
originally dispatched by plugin-type ordering (`_is_old_style_detector()` checked
before `_is_old_style_actuator()`), which made the actuator path unreachable for
combined plugins and caused `_grab_in_flight` to block actuator position reads.

Fixed by adding a `role` field to `_ReadGroup` (and solo tracking) and a
`_resolve_role()` helper. `start_grab` now accepts an optional `role='auto'`
parameter. Explicit `role='actuator'` or `role='detector'` lets callers target one
side of a combined plugin directly; `'auto'` resolves to `'detector'` for
plugins with `ini_detector` and `'actuator'` otherwise.

```python
# Combined plugin: two independent groups, each with its own role
ct.start_grab('axis_x', 100.0, group='actuator', role='actuator')
ct.start_grab('image',  500.0, group='detector', role='detector')
```

A detector grab in-flight (`_grab_in_flight=True`) no longer blocks the actuator
group tick — position reads (`get_actuator_value`) are synchronous and conflict-free.

**Plugin-type detection**:

| Condition | Plugin type |
|---|---|
| has `open` but not `ini_stage`/`ini_detector` | New-style |
| has `ini_stage` only | Old-style actuator |
| has `ini_detector` only | Old-style detector |
| has both | Combined (actuator + detector) |

**`ControlCommand` enum**: `HOME` / `STOP` passed as `value` in `request_write`
to distinguish hardware commands from numeric targets.

**`request_snap(channel, Naverage)`**: one-shot snap, separate from the grab
timer path, passes `Naverage` to the plugin when it declares
`hardware_averaging = True`.

---

## Phase 3a — ControllerThreadModule base class ✅

`ct_module.py` provides `ControllerThreadModule(ParameterControlModule)`:

```
ControllerThreadModule
├── init_hardware(do_init)     attach / detach from registry
├── _detach_controller()       disconnect signals, release registry ref
├── _on_hardware_status()      update UI init indicator, emit init_signal
├── _relay_hw_settings_change  hw_settings edit → ct.update_settings
├── _on_hw_settings_changed    plugin settings change → local or shared tree
└── _module_value_changed      local hw_settings edit → ct + shared tree mirror
```

**Per-channel parameters** (`_PER_CHANNEL_PARAMS` frozenset):
Parameters listed here are kept in each module's LOCAL settings and never
mirrored to the shared `hw_settings`. For `DAQ_Move` this is
`{'units', 'epsilon', ('controller', 'axis')}`. Changes from the CT filtered by
channel name before writing to local settings.

**Second-subscriber synthetic init**: when a second DAQ module attaches to an
already-running CT, it fires a synthetic `hardware_status(True)` so
`_on_hardware_connected()` runs and the module gets its initial state (channel
set, units synced, etc.) without waiting for a real hardware event.

**Subclass hooks**:
- `_get_plugin_class()` — return the plugin class for the selected instrument
- `_connect_ct_signals(ct)` / `_disconnect_ct_signals(ct)` — module-specific signal wiring
- `_on_hardware_connected()` — triggered on hardware_status(True)
- `_derive_channel()` — return this module's channel name (default `''`)
- `_on_per_channel_param_changed(path, data)` — respond to per-channel param updates

---

## Phase 3b — HardwareWidget (designed, not started)

### What to share and what not to

**Share**: the `hw_settings` Parameter panel (hardware configuration). Only one
copy should ever be open per controller. A shared `QAction` achieves this — the
same panel is shown regardless of which module's toolbar triggered it.

**Do NOT share**: the Init action. Each module must call its own `init_hardware()`
to register with the registry, derive its channel, and connect CT signals.
A shared Init button could only call one module's function, leaving others
unregistered. Each DAQ module keeps its own Init button.

**Axis selection** is already per-channel (in `_PER_CHANNEL_PARAMS`), so it is
never synchronised across modules. No special handling needed.

### Planned HardwareWidget

```
DAQ_Move_X toolbar:  [⚙ Settings] [Init] [Move abs] [Stop]  ● connected
DAQ_Move_Y toolbar:  [⚙ Settings] [Init] [Move rel] [Stop]  ● connected
DAQ_Viewer toolbar:  [⚙ Settings] [Init] [Grab]     [Stop]  ● connected
                          ↑
                    shared QAction — opens one shared hw_settings panel
```

The `⚙ Settings` QAction is created once per `ControllerKey` and added to
multiple toolbars. Qt propagates enabled/checked/icon changes to all of them
automatically. The Settings panel shows the shared `hw_settings` Parameter.

The coloured dot reflects `hardware_status` from the CT and appears identically
across all modules sharing the controller.

### Channel status view (`group_snapshot`)

`ControllerThread` exposes a read-only property:

```python
@property
def group_snapshot(self) -> dict:
    return {
        'groups': {
            name: {
                'period_ms': rg.period_ms,
                'channels': {ch: s.sub_count for ch, s in rg.channels.items()},
                'grab_in_flight': self._grab_in_flight and self._pending_group == name,
            }
            for name, rg in self._groups.items()
        },
        'solo': {ch: s.sub_count for ch, (s, _) in self._solo.items()},
        'connected': self._plugin is not None,
    }
```

This powers an on-demand status dialog in HardwareWidget showing active groups,
per-channel subscriber counts, current grab rate, and in-flight state. Useful
for diagnosing rate-inheritance surprises (why is X polling at 100 ms when I
asked for 200?) and confirming channel routing for combined instruments.

**Status**: `group_snapshot` property is implemented on `ControllerThread`.
The HardwareWidget dialog that surfaces it is **deferred** (not started).

---

## Phase 4 — Old-style plugin adapters

Core paths implemented and tested:
- Old-style actuator (`ini_stage` / `move_abs` / `poll_moving`)
- Old-style detector (`ini_detector` / `grab_data` / `stop`)
- Combined plugin (both interfaces, shared `_controller` SDK object)
- Unit conversion in `_to_plugin_units` (float plugins vs DataActuator plugins)
- `_StatusSig` forwarding: `check_position` → `data_ready`, `update_settings` →
  `settings_changed`, plain text → `status_message`

Remaining: edge-case regression tests for
- Multi-axis plugins that set `axis_name` before each `get_actuator_value`
- Plugins that emit `dte_signal` from a hardware-SDK callback thread
- Plugins with `hardware_averaging = True`

---

## Phase 5 — Deprecate master/slave parameter tree ✅

`controller_status` (Master/Slave selector) is now a hidden, read-only no-op in
every parameter tree. `controller_ID` is kept — it still drives `ControllerKey`
derivation in `ControllerThreadModule.init_hardware`. Existing preset XML files
load without errors because the parameter node is still present; users no longer
see the dropdown.

Changes landed:

- `create_controller_param` — `controller_status` gains `visible=False,
  readonly=True`.
- `ParameterControlModule.master` getter — always returns `True`; no longer reads
  `controller_status` from settings.
- `ParameterControlModule.master` setter — emits `DeprecationWarning`, no-op.
- `ExperimentManager._group_plugins_by_id` — removed `sort(key=lambda p:
  p["status"])`; plugins within a group keep preset order.
- `ExperimentManager.list_control_modules_from_preset` — removed `plug["status"]`
  read.
- `ExperimentManager.create_control_modules_from_preset` — removed master/slave
  validation, `master_controller` tracking, `module.master = True`, and
  `controller=master_controller` argument; every module calls `init_module(module)`.
- `ExperimentManager._init_module_master_slave` (old-preset path) — simplified to
  call `init_module(module)`.
- `ExperimentManager.create_control_modules_from_old_preset` — removed
  `master_controller` variable; simplified init loop.

**Deprecation cleanup** (next release — remove these):
- `controller_status` field from `create_controller_param`
- `ControllerStatus` enum in `thread_commands.py`
- `MasterSlaveError` exception and its import in `experiment_manager.py`
- `_init_module_master_slave` method
- `is_master` property on `DAQ_Move_base` / `PluginBase`

---

## Design decisions

### CR-1 — Controller key: hardware_class, not plugin class

```python
hw_cls = getattr(type(self.plugin), 'hardware_class', type(self.plugin))
key = ControllerKey(hardware_class=hw_cls, controller_id=controller_id)
```

Plugins that share physical hardware declare the same `hardware_class` attribute.
Fallback to `type(plugin)` for plugins without it — existing single-role plugins
need no changes.

### CR-2 — Settings: single Parameter, multiple ParameterTree views

One `hw_settings` Parameter object (GUI thread, owned by registry). All
`ParameterTree` panels are views of this object. Per-channel params (`units`,
`epsilon`, axis selection) stay in each module's local settings tree.

### CR-3 — Fully async: CT never blocks callers

All acquisition is request→signal. Old-style actuator polling runs in the
hardware thread's event loop — callers are never blocked.

### CR-5 — Scan engine compatibility

`DAQ_Move` re-emits `move_done_signal` from `change_done` filtered by channel
name. `DAQ_Scan` sees no change.

### CR-6 — Registry test isolation

Pass a fresh `ControllerRegistry()` instance to objects under test.
`registry.close_all()` in teardown.

### CR-7 — QTimer thread affinity

`QTimer` instances for grab groups are created inside `_update_group()` which is
called from a CT slot (hardware thread event loop). They are automatically
affiliated with the hardware thread. No explicit `moveToThread` needed.

### CR-9 — Capabilities integration (future)

In the capabilities-first model, `ControllerThread` emits `capabilities_signal`
after `ini_hardware`. A `HardwareWidget` or dashboard preset loader receives
capabilities and auto-creates DAQ modules for each channel. Each auto-created
DAQ calls `registry.attach()` as a guest.

The named-group API (`start_grab(..., group='actuator')`) will be driven
automatically from Capabilities once `Capabilities` declares channel coupling
groups — a plugin's `Capabilities` will specify which channels are read together
in one hardware transaction, mapping directly to the `group` argument.

### CR-10 — Named read groups

One QTimer per named group per CT. Default group `''` covers the common
single-plugin and multi-axis-simultaneous-read cases. Separate groups for
combined instruments (actuator + detector on same SDK) let the fast axis-position
poll and the slow camera grab run at independent rates with independent
grab-in-flight guards.

Grab serialisation uses a single `_grab_in_flight` flag (not per-group) because
a single plugin instance can only execute one `grab_data()` at a time regardless
of which group triggered it.

### CR-11 — HardwareWidget scope

Shared `⚙ Settings` QAction per controller: yes.
Shared `Init` QAction: **no** — each module must register independently.
Axis selection: per-module only, never shared (already enforced by `_PER_CHANNEL_PARAMS`).
Channel status view: on-demand dialog driven by `group_snapshot`, part of HardwareWidget.

---

## What stays unchanged

| Component | Status |
|---|---|
| `Capabilities` / `Observable` / `Variable` hierarchy | Unchanged |
| `DAQ_Plugin_base.query_data` / `change_to` interface | Unchanged |
| Plugin file/class naming (`DAQ_Move_MyStage`) | Unchanged |
| `DAQ_Scan` / `DAQ_PID` signal interface | Unchanged — `move_done_signal` preserved |
| LECO Actor | Sits on top of `ControllerThread` as another subscriber |
| Old-style plugin API (`ini_stage`, `grab_data`, etc.) | Unchanged |
