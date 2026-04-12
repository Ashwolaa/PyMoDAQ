# ControllerThread Architecture Plan

**Goal**: move PyMoDAQ from "one hardware thread per GUI module" to "one hardware
thread per physical controller, with multiple lightweight GUI subscribers".

This removes the master/slave race condition, simplifies new-plugin authoring, and
makes it possible to attach arbitrary numbers of GUI frontends (DAQ_Move,
DAQ_Viewer, scan engines, dashboards) to the same instrument without conflict.

---

## Current state (baseline)

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
- One QThread **per GUI module**, regardless of shared hardware.
- Master/slave is a raw Python object reference hand-off — no mutex, no queue.
- `DAQ_HardwareWorker` serialises within one plugin's thread only; cross-module
  conflicts are still possible.
- Plugin authors must understand Qt threading to write correct plugins.

---

## Target architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  GUI thread                                                      │
│                                                                  │
│  HardwareWidget  (one per physical controller)                   │
│    owns: shared Parameter model  ← single authoritative settings │
│    owns: QAction "Settings"  ─┐  shared across all child        │
│    owns: QAction "Init HW"   ─┤  DAQ toolbars via QAction       │
│    shows: status indicator    ─┘  sharing (Qt built-in)          │
│         │                                                        │
│    ┌────┴──────────────────┬─────────────────┐                   │
│    ▼                       ▼                 ▼                   │
│  DAQ_Move_1           DAQ_Move_2        DAQ_Viewer_1             │
│  main_settings        main_settings     main_settings            │
│  [Settings▸][Init▸]   [Settings▸][Init▸]  [Settings▸][Init▸]    │
│  [Move abs] [Stop]    [Move rel] [Stop]   [Grab]     [Stop]      │
│    │  ↕                   │  ↕               │  ↕                │
│  ParameterTree        ParameterTree      ParameterTree           │
│  (view, on demand)    (view, on demand)  (view, on demand)       │
│    └────────────────────┴─────────────────┘                      │
│                   all views share the same Parameter model       │
└──────────────────────────────┬───────────────────────────────────┘
                               │  queued signals only
┌──────────────────────────────▼───────────────────────────────────┐
│  ControllerThread  (one QThread per physical controller)         │
│                                                                  │
│  owns: plugin instance                                           │
│  owns: SDK / controller object                                   │
│  owns: per-channel QTimer instances (continuous grab)            │
│  holds: read-only ref to shared Parameter (for ini_hardware)    │
│                                                                  │
│  Signals → GUI thread (queued):                                  │
│    data_ready(channel, DataToExport)                             │
│    change_done(channel, DataToExport)                            │
│    hardware_status(connected: bool, info: str)                   │
│    settings_changed(path, data, change)  → Parameter.setValue()  │
│    capabilities_signal(Capabilities)                             │
│                                                                  │
│  Slots ← GUI thread (queued):                                    │
│    ini_hardware()                                                │
│    request_read(channel)                                         │
│    request_write(channel, value)                                 │
│    start_grab(channel, continuous)                               │
│    stop_grab(channel)                                            │
│    update_settings(path, data, change)  → plugin.commit_settings │
└──────────────────────────────────────────────────────────────────┘
```

**Key ownership rules**:
- `Parameter` model (plugin hardware settings) lives in the GUI thread, owned by
  `HardwareWidget`. `ControllerThread` holds a read-only reference used only at
  `ini_hardware` time. All subsequent writes go through `settings_changed` signal.
- `main_settings` (module name, refresh rate, UI type) stays owned by each
  `DAQ_Move` / `DAQ_Viewer` individually — not shared.
- Plugin instance and SDK object live exclusively in `ControllerThread`'s thread.

Master/slave disappears — replaced by channel subscription.
Plugin interface: `query_data(names, fresh)` + `change_to(name, value)` only.

---

## Migration phases

### Phase 0 — Naming cleanup (trivial, zero behaviour change)

Add aliases; keep old names as deprecated stubs forever:

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

### Phase 1 — ControllerRegistry

Process-global singleton mapping a `ControllerKey` to a live `ControllerThread`.
The shared `Parameter` model is created here, in the GUI thread, before the
hardware thread starts.

```python
# new file: control_modules/controller_registry.py

@dataclass(frozen=True)
class ControllerKey:
    hardware_class: type  # shared driver class (see CR-1); falls back to plugin class
    controller_id: int    # user-assigned grouping integer (0-9999)

class ControllerRegistry:
    """Singleton in production; injectable in tests via constructor."""

    @classmethod
    def get(cls) -> ControllerRegistry: ...   # module-level singleton

    def acquire(
        self,
        key: ControllerKey,
        plugin_class: type,
        params_state: dict | None = None,
    ) -> tuple[ControllerThread, Parameter]:
        """
        Return (thread, shared_parameter) for key.

        First caller: creates the shared Parameter (GUI thread), creates
        ControllerThread, starts QThread, triggers ini_hardware.
        Subsequent callers: return the already-running thread and the
        existing shared Parameter. params_state is ignored for guests.
        """

    def release(self, key: ControllerKey) -> None:
        """Decrement ref-count; tear down thread+Parameter when count → 0."""

    def close_all(self) -> None:
        """Tear down all threads — used in test teardown."""
```

**Deliverable**: registry shell + unit tests (no GUI changes yet).

---

### Phase 2 — ControllerThread

The object that lives in the hardware thread, owns the plugin, and serialises
all hardware access. Qt's queued connection mechanism already serialises
concurrent `request_read` / `request_write` calls — no separate scheduler
object is needed at this stage.

```python
# new file: control_modules/controller_thread.py

class ControllerThread(QObject):

    # Signals → GUI thread (all queued by Qt cross-thread delivery)
    data_ready          = Signal(str, object)   # (channel, DataToExport)
    change_done         = Signal(str, object)   # (channel, DataToExport | None)
    hardware_status     = Signal(bool, str)     # (connected, info)
    settings_changed    = Signal(list, object, str)  # (path, data, change)
    capabilities_signal = Signal(object)        # Capabilities

    def __init__(self, plugin_class: type, settings: Parameter) -> None:
        super().__init__()
        self._plugin_class = plugin_class
        self._settings_ref = settings   # GUI-thread Parameter — read-only here
        self._plugins: dict[type, Any] = {}  # plugin_class → plugin instance
        self._controller = None          # shared SDK object, set by first ini_hardware
        self._grab_timers: dict[str, QTimer] = {}  # continuous grab timers

    # ── Slots (all execute in hardware thread via queued connection) ──────────

    @Slot()
    def ini_hardware(self) -> None:
        """Instantiate plugin, open hardware, wire plugin signals."""

    @Slot()
    def close_hardware(self) -> None:
        """Close plugin, stop timers, emit hardware_status(False, 'closed')."""

    @Slot(str)
    def request_read(self, channel: str) -> None:
        """One-shot read; emits data_ready(channel, dte)."""

    @Slot(str, object)
    def request_write(self, channel: str, value) -> None:
        """Write value to channel; emits change_done when complete."""

    @Slot(str, float)
    def start_grab(self, channel: str, period_ms: float) -> None:
        """Create (or restart) a QTimer for periodic reads on channel."""

    @Slot(str)
    def stop_grab(self, channel: str) -> None:
        """Stop and remove the grab timer for channel."""

    @Slot(list, object, str)
    def update_settings(self, path, data, change) -> None:
        """Relay GUI Parameter edit → plugin.commit_settings()."""
```

`QTimer` instances are created inside `@Slot` methods so they are always
affiliated with the hardware thread's event loop. No explicit `moveToThread`
needed for child objects.

**Serialisation**: Qt queues `request_read` and `request_write` calls in the
hardware thread's event loop. Each slot runs to completion before the next
starts — no mutex or scheduler needed.

**Async acquisition contract** (see CR-3):
- Old-style detectors: `request_read` calls `grab_data()`; plugin's `dte_signal`
  is wired to emit `data_ready`. No blocking.
- Old-style actuators: `request_write` calls `move_abs` then polls (simple loop
  with `QCoreApplication.processEvents` guard) until epsilon reached, emits
  `change_done`. No blocking from the caller's perspective.
- New-style plugins: `query_data` / `change_to` called directly; results emitted
  immediately.

**Multiple plugin instances** (legacy mixed DAQ_Move + DAQ_Viewer case):
When two plugin classes share the same `hardware_class`, both land in the same
`ControllerThread`. The thread opens the SDK once (first `ini_hardware` call)
and stores `self._controller`. The second plugin class is initialised with the
already-open `self._controller` reference — exactly the current master/slave
hand-off, but now correctly serialised through a single thread.
`request_read` / `request_write` dispatch to the appropriate plugin instance
based on the channel name declared in `Capabilities`.

**Capabilities-first plugin**: a unified plugin that exposes both axes and
observables lives as a single instance in `self._plugins`. No second plugin
class is needed. DAQ_Move and DAQ_Viewer are purely GUI subscribers to
different channels of that one instance (see CR-9).

**Future**: if batching (one hardware read fans out to multiple subscribers) or
priority queueing becomes necessary, a `ChannelScheduler` child `QObject` can be
introduced at that point without changing the public slot/signal interface.

**Deliverable**: `ControllerThread` + integration tests with mock plugin
(headless, no GUI).

---

### Phase 3a — DAQ_Move / DAQ_Viewer become thin channel subscribers

Two acquisition paths converge on the same subscriber interface.

#### Path A — Legacy (user manually picks plugin class)

Each GUI module:
1. Derives a `ControllerKey` from its `main_settings`
   (`hardware_class = getattr(plugin_cls, 'hardware_class', plugin_cls)`).
2. Calls `ControllerRegistry.acquire(key, plugin_class, params_state)`.
   - First caller: creates thread, opens hardware.
   - Subsequent callers: get the running thread; `params_state` ignored.
3. Receives back `(controller_thread, shared_parameter)`.
4–7. Connects channels, signals, settings relay; calls `release(key)` on close.

#### Path B — Capabilities-first (DAQs created from Capabilities)

1. `HardwareWidget` (or dashboard preset loader) calls `registry.acquire(key, plugin_class)`
   — this is the sole "owner" acquire that creates the thread.
2. `ControllerThread` runs `ini_hardware`, emits `capabilities_signal(Capabilities)`.
3. `HardwareWidget` receives capabilities and auto-creates DAQ_Move / DAQ_Viewer
   instances for each axis / observable.
4. Each auto-created DAQ calls `registry.acquire(key, ...)` as a guest — gets
   the already-running thread, ref_count incremented.
5. Each DAQ subscribes to its channel name exactly as in Path A.
6. `HardwareWidget` holds its own ref; as long as it exists the thread stays
   alive even if all child DAQs close.

**Common subscriber interface** (both paths):
- Connect `controller_thread.data_ready` / `change_done`, filter by channel name.
- Re-emit `move_done_signal` / `grab_done_signal` for scan engine compatibility.
- No owned `QThread`, no `ActuatorWorker`, no master/slave subtree.

**What DAQ_Move retains**:
- `main_settings` (module name, UI type, refresh rate) — not shared
- Per-module toolbar actions (move abs/rel/home, stop)
- `move_done_signal` — re-emitted from `change_done` filtered by channel name

**What disappears from DAQ_Move**:
- Owning a `QThread` / `ActuatorWorker`
- `send_param_status` / `update_settings` broadcast round-trips
- Master/slave parameter subtree

**Deliverable**: refactored `DAQ_Move` + `DAQ_Viewer`; existing test suite passes.

---

### Phase 3b — HardwareWidget (ideal end state, follow-on to 3a)

Once the threading model is stable, extract the two shared concerns from every
DAQ toolbar into a dedicated `HardwareWidget`:

```
HardwareWidget  (one per ControllerThread / physical controller)
  owns: shared Parameter model
  owns: QAction "Settings"    ← shared across child DAQ toolbars
  owns: QAction "Init HW"     ← shared across child DAQ toolbars
  shows: coloured status dot (colour matches across all child DAQs)

DAQ_Move_1 toolbar:  [Settings▸] [Init▸] [Move abs] [Stop]
DAQ_Move_2 toolbar:  [Settings▸] [Init▸] [Move rel] [Stop]
DAQ_Viewer toolbar:  [Settings▸] [Init▸] [Grab]     [Stop]
```

A `QAction` added to multiple `QToolBar`s reflects enabled/checked/icon changes
in all of them simultaneously — Qt handles this natively, no `widget_sync` needed
for these two controls.

`widget_sync` is useful for other cross-DAQ UI state that shares the same thread:
e.g. keeping a "connected" status label consistent across multiple DAQ docks that
share the same controller.

**Deliverable**: `HardwareWidget`; reduced DAQ toolbar clutter; settings/init
logic lives in one place per controller.

---

### Phase 4 — Old-style plugin adapters verified and hardened

The `query_data` / `change_to` adapters in `DAQ_Move_base` and `DAQ_Viewer_base`
already exist. This phase ensures they work correctly inside `ControllerThread`
(edge cases: multi-axis plugins, plugins that emit `dte_signal` from a callback
thread, etc.) and adds regression tests for each old-style plugin pattern.

**Deliverable**: no plugin changes required; test coverage for adapter paths.

---

### Phase 5 — Deprecate master/slave parameter tree

Remove `create_controller_param`, `controller_status`, `controller_ID` from
parameter trees. Replace with `ControllerKey` derivation. Keep removed
parameters as deprecated no-ops for one release cycle. Migrate preset XML files.

**Deliverable**: simpler parameter trees; migration tool for existing presets.

---

## What stays unchanged

| Component | Status |
|---|---|
| `Capabilities` / `Observable` / `Variable` hierarchy | Unchanged |
| `DAQ_Plugin_base.query_data` / `change_to` interface | Unchanged |
| Plugin file/class naming (`DAQ_Move_MyStage`) | Unchanged |
| `ChannelControl` GUI rows | Subscribe to `ControllerThread` instead of local worker |
| `DAQ_Scan` / `DAQ_PID` signal interface | Unchanged — `move_done_signal` preserved in DAQ_Move |
| LECO Actor | Sits on top of `ControllerThread` as another subscriber |

---

## Design decisions (Critical Review)

### CR-1 — Controller key: hardware_class, not plugin class

The key must identify the **physical hardware**, not the GUI wrapper.
Using the plugin class as the key causes a silent conflict when the same
physical device is exposed by two separate plugin classes (e.g.
`DAQ_Move_MyStage` for the motor axis and `DAQ_0DViewer_MyStage` for the
on-board temperature sensor): two different keys → two ControllerThreads →
two threads hitting the same SDK simultaneously.

**Resolution**: plugins declare a `hardware_class` attribute pointing to the
shared driver class.  The registry key becomes `(hardware_class, controller_id)`.

```python
# Both point at the same driver → same ControllerThread
class DAQ_Move_MyStage(DAQ_Move_base):
    hardware_class = MyStageDriver

class DAQ_0DViewer_MyStage(DAQ_Viewer_base):
    hardware_class = MyStageDriver
```

Key construction at call site:

```python
hw_cls = getattr(type(self.plugin), 'hardware_class', type(self.plugin))
key = ControllerKey(hardware_class=hw_cls, controller_id=self.settings['controller_ID'])
```

**Fallback**: if `hardware_class` is not declared, `type(plugin)` is used —
existing single-role plugins (the vast majority) need no changes.

**Capabilities-first plugins**: a unified plugin that implements both
`query_data` and `change_to` has no split, so `hardware_class` defaults to
`type(plugin)` and the key is unique by construction.

**Long-term**: replace `controller_id` with a user-supplied physical address
(COM port, IP, USB serial number) once plugins are ready to expose it.

---

### CR-2 — Settings: single Parameter model, multiple ParameterTree views

The entire sync problem is eliminated by eliminating copies.

`HardwareWidget` (GUI thread) owns one `Parameter` object — the authoritative
hardware settings model. All DAQ `ParameterTree` panels are views of this same
object. pyqtgraph's direct connections within the GUI thread propagate changes to
all views automatically.

```
HardwareWidget.settings  (Parameter, GUI thread)
    ├── ParameterTree panel (DAQ_Move_1, on demand)
    ├── ParameterTree panel (DAQ_Move_2, on demand)
    └── ParameterTree panel (DAQ_Viewer_1, on demand)

ControllerThread  (hardware thread)
    holds read-only reference to settings
    emits settings_changed(path, data, change) → HardwareWidget slot
        → Parameter.setValue()  ← always in GUI thread
        → pyqtgraph propagates to all open ParameterTree views
```

User edits flow in reverse:

```
ParameterTree (any panel) → Parameter.sigTreeStateChanged (GUI thread, direct)
    → HardwareWidget slot → ControllerThread.update_settings (queued)
        → plugin.commit_settings()  ← hardware thread
```

**What disappears**: `send_param_status`, `update_settings` broadcast,
subscriber lists, `saveState()` round-trips, echo-prevention disconnects.

**Guest params_state**: silently ignored when hardware is already live. Guest
receives the live shared Parameter reference. Status bar warns if guest's preset
conflicts with live state.

**`widget_sync` role**: intra-module widget consistency only (e.g. spinbox + label
showing the same value). Not used cross-module or cross-thread.

---

### CR-3 — Fully async: ControllerThread never blocks callers

`ControllerThread` has no synchronous data return. All acquisition is
request→signal:

- **New-style** (`query_data` returns data): slot calls `query_data`, emits
  `data_ready` immediately.
- **Old-style detector** (`grab_data` fire-and-forget): slot calls `grab_data()`;
  plugin's `dte_signal` is wired to emit `data_ready`. No blocking.
- **Old-style actuator** (`move_abs` + polling): slot calls `move_abs` then
  polls inline (simple loop) until epsilon reached, emits `change_done`. Because
  this runs in the hardware thread's event loop, callers are never blocked — they
  have already returned to their own event loop.

All subscribers receive `data_ready` / `change_done` and filter by channel name.
This pattern is already how Qt event-driven code works — the existing
`ThreadCommand` mechanism is the same concept, just centralised here.

---

### CR-4 — Resolved by CR-2

No additional sync mechanism needed.

---

### CR-5 — Scan engine compatibility: channel-name filtering

`DAQ_Scan` expects `move_done_signal` per `DAQ_Move`. This is preserved:

```python
# DAQ_Move subscribes to its channel name
controller_thread.change_done.connect(self._on_change_done)

def _on_change_done(self, channel: str, dte):
    if channel == self._channel_name:
        self.move_done_signal.emit(dte)   # DAQ_Scan sees no change
```

Two axes moving concurrently have different channel names → no collision,
no request tokens needed.

---

### CR-6 — Registry test isolation

`ControllerRegistry` accepts an optional constructor argument for injection.
Production: module-level singleton via `ControllerRegistry.get()`. Tests: fresh
instance per test, torn down via `registry.close_all()` in teardown.

---

### CR-7 — QTimer thread affinity

`QTimer` instances for continuous grab are created inside `@Slot` methods
(i.e. inside the hardware thread's event loop), so they are automatically
affiliated with that thread. No explicit `moveToThread` call is needed.

If a `ChannelScheduler` child `QObject` is introduced in the future, the same
rule applies: create it inside a hardware-thread slot and it inherits the
correct thread affinity.

---

### CR-9 — Capabilities integration: ControllerThread as the source

In the capabilities-first model the flow is **inverted** relative to the legacy
path: instead of DAQ modules pulling from the registry, the `ControllerThread`
pushes capabilities outward and the dashboard/HardwareWidget creates DAQs from
them.

```
ControllerThread
    │ ini_hardware()
    ▼
capabilities_signal(Capabilities)
    │
    ▼
HardwareWidget
    ├── creates DAQ_Move  "axis_x"   → acquire(key) as guest → subscribe channel
    ├── creates DAQ_Move  "axis_y"   → acquire(key) as guest → subscribe channel
    └── creates DAQ_Viewer "temp"    → acquire(key) as guest → subscribe channel
```

**No conflict**: the unified plugin has one class → one key → one thread.
DAQ_Move and DAQ_Viewer are GUI views over different channels of the same plugin;
they never independently open the hardware.

**Mixed legacy case** (`hardware_class` declared on separate plugin classes):
Both plugin classes resolve to the same key. The thread hosts both plugin
instances sharing one `self._controller` SDK object. Channel dispatch routes
`request_read` / `request_write` to whichever plugin instance owns that channel
name according to `Capabilities`.

**Key invariant**: `ControllerThread` is always the single point of hardware
ownership. DAQ_Move and DAQ_Viewer are always pure subscribers — they never
touch the SDK directly.

---

### CR-8 — LECO Actor layering

`ControllerThread` = in-process ownership. LECO Actor = network exposure on top.

```
Network clients (LECO Directors)
        ↓ RPC / ZMQ
   LECO Actor  ←── subscriber to ControllerThread (like any DAQ module)
        ↓
  ControllerThread
        ↓
   Plugin / SDK
```

---

## Resolved open questions

### OQ-1 — Hot-swap: disconnect / reconnect

`hardware_status = Signal(bool, str)` on `ControllerThread`.

- **Disconnect** (exception in `query_data` / `change_to`, or watchdog):
  `ControllerThread` emits `hardware_status(False, reason)`. All DAQ GUIs
  transition to disabled state; grab timers are stopped.
- **Reconnect**: only the owner DAQ (first `acquire()` caller) can trigger
  re-init. `ControllerThread` re-runs `ini_hardware`, emits
  `hardware_status(True, info)`. Guest DAQs resume automatically with no extra
  logic.

### OQ-2 — Priority queue (deferred, not a priority)

Emergency stop via direct-connection slot if needed later.

### OQ-3 — ini_hardware ownership and HardwareWidget

See Phase 3b. Single owner model: first `acquire()` caller triggers init.
`HardwareWidget` is the eventual UI owner. Visual grouping indicator (coloured
dot) makes controller grouping visible in the dashboard.

### OQ-4 — Preset compatibility (deferred to Phase 5)

Backward-compatible loading for one release cycle; migration tool provided.

### OQ-5 — Parameter thread safety: model stays in GUI thread

`Parameter` is a pyqtgraph `QObject` with thread affinity. Calling `setValue()`
from the hardware thread is unsafe. Resolution: `Parameter` lives in the GUI
thread (owned by `HardwareWidget`). `ControllerThread` emits `settings_changed`
(queued) → GUI thread slot calls `setValue()`. Thread-safe by construction.
