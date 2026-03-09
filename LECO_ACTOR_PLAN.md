# PyMoDAQ LECO Actor/Director/Spectator — Implementation Plan

## Motivation

The current architecture has two structural problems this plan addresses:

1. **Thread contention on shared hardware.** When a `DAQ_Move` and a `DAQ_Viewer` share the
   same physical instrument, both run hardware plugins in separate threads and both query the
   device concurrently. This is not well handled by most driver connections.

2. **The master/slave model is process-local.** Sharing a hardware controller across modules
   requires them to live in the same process, with a fragile ID-matching mechanism. Remote
   sharing (across machines) requires the current "fake plugin" LECO workaround, where a
   `DAQ_Move_LECODirector` or `DAQ_xDViewer_LECODirector` masquerades as a hardware plugin
   while actually forwarding commands over LECO to a module that owns the real hardware.

**Solution:** make the hardware the actor. Directors (DAQ_Move, DAQ_Viewer) and spectators
connect to it over LECO. The actor's single event loop serializes all hardware access
naturally, eliminating thread contention and the master/slave pattern.

---

## Conceptual Model

```
   ┌─ Machine A (hardware side) ──────────────────────────────────┐
   │                                                              │
   │   LECO Coordinator ◄──────────────── (links to other        │
   │         |                             Coordinators)          │
   │   Data Proxy (ZMQ XPUB/XSUB)                                │
   │         |                                                    │
   │   PymodaqActor                                               │
   │     ├── RPC methods ──────────────► Coordinator             │
   │     └── DataPublisher ────────────► Data Proxy ─────────┐   │
   └──────────────────────────────────────────────────────────┼──┘
                                                              │
   ┌─ Machine B (client side) ────────────────────────────────┼──┐
   │                                                          │   │
   │   Director(s)          ─── RPC via Coordinator ──────►  │   │
   │   (DAQ_Move, DAQ_Viewer,                                 │   │
   │    SettingsAxis)                                         │   │
   │                                                          │   │
   │   Spectator(s)         ─── ZMQ SUB ◄────────────────────┘   │
   │   (subscribe-only)                                           │
   └──────────────────────────────────────────────────────────────┘
```

**Deployment requirement:** the actor only needs to be connected to a Coordinator. That
single requirement enables everything else:

- **Directors** on any machine reach the actor via LECO's Coordinator routing
  (`namespace.actor_name` addressing). Coordinators on different machines can be linked,
  making this transparently cross-machine.
- **Spectators** additionally need the **Data Proxy** to be reachable. The proxy is a
  lightweight separate process (`pyleco`'s built-in proxy) that fans out ZMQ PUB frames
  to all subscribers. In practice the Coordinator and Data Proxy run together on the
  hardware machine; clients point at the same host for both.
- **Same-machine use** (the common case during development) works with no network
  configuration — Coordinator, Data Proxy, Actor, and Directors/Spectators all on
  `localhost`.

### Roles

| Role | Controls hardware? | Sends data? | Receives data? |
|---|---|---|---|
| **Actor** | yes (exclusively) | publishes (data channel) | receives RPC commands |
| **Director** | via RPC only | sends RPC commands | receives RPC responses + data channel |
| **Spectator** | no | no | subscribes (data channel only) |

### Observable vs Variable

Every quantity a hardware instrument exposes falls into one of two categories:

- **Observable** — something we can *measure*. Read-only from the outside. A `DAQ_Viewer`
  director is built on observables.
- **Variable** — something we can *change*. Read-write. A `DAQ_Move` director requires at
  least one variable. Every `Variable` is also an `Observable`.

These are **purely descriptive metadata objects** — they carry no callable getters. The
plugin's existing `grab_data` / `get_actuator_value` mechanisms remain the reading path;
the actor wires them up. Observable/Variable metadata serves three purposes:

1. **UI introspection** — when a director connects to an actor, `get_capabilities()` RPC
   returns the actor's declared capabilities so the Dashboard can show what is available.
2. **Settings-as-actuator** — `SettingsAxisDirector` reads the actor's `Variable` list to
   know which parameters it can drive, with their bounds and units.
3. **Type checking** — a `DAQ_Move` director asserts the actor has at least one `Variable`;
   a `DAQ_Viewer` director asserts at least one `Observable`.

Callable getters are explicitly deferred: they cannot be serialized over LECO, would couple
the metadata object to a live plugin instance, and duplicate the existing reading mechanisms.

---

## Unified hardware interface

At the hardware level, all instrument interaction reduces to two operations:

```python
# Both forms accepted:
query_data(names: str | list[str] | None, fresh: bool) → DataToExport | None
change_to(name: str | list[str], value: Any | list[Any]) → None
```

Both `query_data` and `change_to` accept singular or plural forms:
- `query_data(names='spectrum')` and `query_data(names=['spectrum', 'temperature'])` are
  both valid; a bare string is normalized to a one-element list before forwarding to
  `device.read()`.
- `change_to('position', 10.0)` moves one axis; `change_to(['x', 'y'], [1.0, 2.0])`
  writes two variables in a single RPC call, calling `device.write()` once per pair.

### `fresh` semantics

| `fresh=True` | `fresh=False` |
|---|---|
| Trigger new hardware acquisition, publish result on data channel | Return actor's internal `_last_data` cache without touching hardware |
| Used by directors that need an up-to-date measurement | Used by directors that want the last known state without disturbing ongoing hardware |
| Costly (hardware settling / integration time) | Free (memory read) |

**Important:** `get_actuator_value` maps to `query_data(fresh=True)`. It polls the real
hardware position and is the mechanism by which a `DAQ_Move` director detects when a motion
has completed (the returned position is compared against the target). A cached value would
give a false "move done" signal.

**Spectators do not call `query_data` at all.** They subscribe to the ZMQ PUB data channel
and receive whatever the actor's periodic `read_publish` timer produces. The `fresh=False`
RPC is a narrower use case: a director that wants the last known state without triggering
new hardware activity (e.g., logging a position mid-scan without interrupting motion).

### Legacy method aliases (Phase 1 → Phase 2 transition)

To keep existing director plugins working unchanged during the transition:

| Old RPC method | Maps to |
|---|---|
| `grab()` | `query_data(fresh=True)` — continuous acquisition |
| `snap()` | `query_data(fresh=True)` — single acquisition |
| `stop_grab()` | internal flag to interrupt continuous grab |
| `move_abs(pos)` | `change_to('position', pos)` |
| `move_rel(pos)` | `change_to('position', current + pos)` |
| `move_home()` | `change_to('position', home)` |
| `get_actuator_value()` | `query_data(fresh=True)` — polls real hardware position |

Old method names are registered on the actor as `register_rpc_method(..., name='grab')` etc.,
so `DAQ_Move_LECODirector` / `DAQ_xDViewer_LECODirector` code requires no changes in Phase 1.

### Director / Spectator separation — architectural invariant

**The control channel (RPC) must always be responsive, regardless of data rate.**

Directors and Spectators have strictly separate roles:

| | Director | Spectator |
|---|---|---|
| Channel | RPC only (control protocol) | ZMQ SUB only (data protocol) |
| Sends commands? | yes | **no** |
| Receives data frames? | **no** | yes |
| Can be overwhelmed by data? | **never** | yes — designed to drop frames gracefully |

**pyleco already provides the infrastructure for both channels.** The `ExtendedMessageHandler`
(base of `PipeHandler`) holds both a control socket (via Coordinator) and a ZMQ SUB socket,
polling them together in a single dedicated thread. This means the two channels are already
independent at the network level — a burst of data frames does not block control messages
in the pyleco layer.

**Where the real risk is: the Qt boundary.** The `PipeHandler` thread emits Qt signals into
the main thread. If the main thread is busy rendering a heavy detector frame, the Qt event
queue backs up. A `stop_grab` RPC that arrives in the `PipeHandler` thread is translated to
a Qt signal, queued, and delayed — the operator loses real-time control. This is the actual
failure mode the separation must prevent.

**Solution:** a Spectator owns a `PymodaqDataListener` (a pyleco `Listener` with
`DataSubscriberHandler`) running in its own thread. The `Listener` thread emits data
via a **bounded Qt signal queue (depth 1)**: when a new frame arrives before the
previous one has been consumed by the display, the old frame is silently replaced.
The director's `PipeHandler` thread, handling only small JSON RPC messages, is never
touched by this backpressure.

A plugin such as `DAQ_xDViewer_LECODirector` owns **both** objects:

```
DAQ_xDViewer_LECODirector
  ├── PymodaqDetectorDirector  ─── RPC ───►  Actor  (snap / grab / stop_grab / ...)
  │     └── PipeHandler thread  ← JSON only, always fast
  └── PymodaqDataListener       ◄── ZMQ ───  Actor  (data frames, independent thread)
        └── DataSubscriberHandler thread  ← bounded queue, drops frames if slow
```

**For a standalone Spectator** (Phase 4), only the `PymodaqDataListener` half is needed —
no director, no `PymodaqDetectorDirector`, no RPC. pyleco's `Listener` can be used without
registering to a Coordinator at all if no control is needed; the SUB socket connects directly
to the data proxy.

**Move directors** (`DAQ_Move_LECODirector`, `DAQ_Move_SettingsAxis`) do **not** need a
Spectator at all. Move-done detection is a periodic `query_data(fresh=True)` RPC call —
small JSON, never competing with data frames.

### Multi-hardware spectators and synchronization

A spectator can subscribe to multiple actors simultaneously, holding a
`_cache: dict[actor_name, DataToExport]`. Three sync modes (selectable in `SpectatorWidget`):

| Mode | Behaviour | When to use |
|---|---|---|
| **latest** | Recompute on every incoming frame using latest cached value from all actors | Slow-drifting signals, commutative operations |
| **barrier** | Wait for at least one new frame from every subscribed actor before recomputing | Actors triggered by the same scan step |
| **timestamp** | Match frames within a configurable time window using `DataToExport.timestamp` | Independent actors at different rates where simultaneity matters |

---

## Architecture of Key New Classes

### `PymodaqActor` (Phase 1) ✅

Wraps `pyleco.actors.Actor` (v0.6). Pure Python, **no Qt dependency**.

```
PymodaqActor(pyleco.actors.Actor)
    device: <duck-typed>                       # any object with read()/write()
    publisher: DataPublisher                   # ZMQ PUB, built into pyleco.actors.Actor
    _director_registry: set[str]               # full names of connected directors
    _last_data: DataToExport | None            # cache for fresh=False queries

    # Primary interface (control channel RPC) — singular and plural accepted:
    query_data(names: str|list|None, fresh: bool)   # str auto-wrapped in list
    change_to(name: str|list, value: Any|list)      # list → iterate zip(name, value)

    # Introspection (control channel RPC):
    get_capabilities() → dict                  # serialized Capabilities (kind discriminator)
    get_pymodaq_settings() → str | None        # XML parameter tree
    set_info(path, value)                      # update setting, broadcast to directors
    subscribe_director(name: str)              # register for settings broadcasts
    unsubscribe_director(name: str)

    # Legacy aliases (registered as separate RPC method names):
    grab / snap / stop_grab                    # → query_data(fresh=True)
    move_abs / move_rel / move_home            # → change_to('position', ...)
    get_actuator_value                         # → query_data(fresh=True)

    # Data channel (ZMQ PUB, via inherited DataPublisher):
    read_publish(device, publisher)            # periodic: publish DataToExport
```

**Settings broadcast:** `set_info` calls `set_director_settings` RPC on every name in
`_director_registry`. Last-write-wins. Conflict resolution is deferred.

### `PymodaqMoveDirector` / `PymodaqDetectorDirector` (Phase 2)

Typed wrappers around `pyleco.directors.Director`. Replace the existing `ActuatorDirector`
/ `DetectorDirector` in `director_utils.py`. Extended with:
- `subscribe_settings()` — calls `subscribe_director` RPC so this director receives
  settings broadcasts automatically.
- `get_capabilities()` — retrieves the actor's `Capabilities` for UI display.

### `SpectatorSubscriber` (Phase 4)

A `QObject` worker that subscribes to the actor's data channel via ZMQ SUB. Emits
`data_received(str, DataToExport)` (topic + data) as a Qt signal into the main thread.
Does not send any RPC commands — purely passive.

---

## Phase 0 — Observable/Variable data model ✅ COMPLETE

**Goal:** Establish vocabulary. Non-breaking, additive only.

**Location:** `pymodaq/control_modules/capabilities.py` (new file) ✅

Rationale: Observable/Variable describes *hardware capability* — what an instrument can do,
before any data is acquired. This is categorically different from `pymodaq_data`'s concern
(data after acquisition). Plugin packages already import from `pymodaq.control_modules`
(`DAQ_Move_base`, `DAQ_Viewer_base`, etc.), so placing it here requires zero extra imports
for plugin authors. It cannot live in `pymodaq_data` (wrong concern) or `pymodaq_utils`
(too domain-specific).

**API (as implemented):**

```python
@dataclass
class Observable:
    """A readable quantity exposed by a hardware instrument."""
    name: str
    label: str = ''
    units: str = ''
    dtype: str = 'float64'
    shape: tuple[int | None, ...] = (1,)   # None = variable-length dimension

@dataclass
class Variable(Observable):
    """Unconstrained read-write quantity. Base class for typed sub-classes."""
    pass   # no constraint fields here

@dataclass
class ContinuousVariable(Variable):
    """Numeric range + move-done tolerance."""
    lo: float | None = None     # lower bound; None = -inf
    hi: float | None = None     # upper bound; None = +inf
    epsilon: float = 0.0        # move-done tolerance (DAQ_Move); 0 = unspecified

@dataclass
class DiscreteVariable(Variable):
    """Finite enumeration of allowed values."""
    choices: list = field(default_factory=list)

@dataclass
class Capabilities:
    observables: list[Observable] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
```

Variable hierarchy:
```
Observable
  └── Variable                  # unconstrained read-write
        ├── ContinuousVariable  # numeric range + epsilon
        └── DiscreteVariable    # finite set of allowed values
```

**`Observable.shape`** accepts `None` in any position to express a variable-length dimension
(e.g. event-list detectors: `shape=(None,)`).

**Serialization:** `Capabilities.to_dict()` uses a `"kind"` discriminator field on each
variable (`"variable"`, `"continuous"`, `"discrete"`); `from_dict()` dispatches to the
correct subclass. `None` shape dimensions and `None` bounds serialize as JSON `null`.

**Opt-in for plugins:**

```python
class MySpectrometer(DAQ_Viewer_base):
    capabilities = Capabilities(
        observables=[Observable('spectrum', units='counts', shape=(1024,))]
    )

class MyStage(DAQ_Move_base):
    capabilities = Capabilities(
        variables=[ContinuousVariable('position', units='mm', lo=-50, hi=50, epsilon=0.001)]
    )

class MyFilterWheel(DAQ_Move_base):
    capabilities = Capabilities(
        variables=[DiscreteVariable('filter', choices=['ND1', 'ND2', 'ND4'])]
    )
```

**Fallback for existing plugins** — `infer_capabilities(plugin_instance) -> Capabilities` ✅:
- If the plugin has `_controller_units` or `_axis_names` → infers one `ContinuousVariable`
  per axis from `_controller_units` (units) and `_epsilons` (epsilon). Single-axis: name
  `'position'`.
- Otherwise → one `Observable` named `'data'` (detector fallback).
- Existing plugins require zero changes.

**Deliverables:** ✅
- `pymodaq/control_modules/capabilities.py`
- `tests/control_modules/test_capabilities.py` — 55 pure-Python tests, all pass

---

## Phase 1 — `PymodaqActor`: headless hardware process ✅ COMPLETE

**Goal:** Solve the thread-contention problem immediately. New code only, zero breaking changes.

**Location:** `pymodaq/utils/leco/actor.py` (new file) ✅

**Deliverables:**

1. **`PymodaqActor`** class ✅. Inherits `pyleco.actors.Actor` (v0.6).
   Accepts any object with a `read(names) -> DataToExport` / `write(name, value)` interface
   as `device_class`. The actor's event loop serializes all hardware access — no threading
   issues by construction.

   Registered RPC methods:
   - **Primary:** `query_data`, `change_to`
   - **Introspection:** `get_capabilities`, `get_pymodaq_settings`, `set_info`,
     `subscribe_director`, `unsubscribe_director`
   - **Legacy aliases:** `grab`, `snap`, `get_actuator_value` → `query_data(fresh=True)`;
     `stop_grab`; `move_abs`, `move_rel`, `move_home`

   **Singular/plural acceptance** (implemented):
   - `query_data(names, fresh)` — `names` accepts `str | list[str] | None`; a bare string
     is wrapped in a list before being forwarded to `device.read()`
   - `change_to(name, value)` — `name` accepts `str | list[str]`; when a list is passed,
     iterates `zip(name, value)` and calls `device.write()` once per pair

2. **CLI entry point (no Qt by default):** ✅
   ```
   pymodaq-actor  →  pymodaq.utils.leco.actor:actor_main
   ```
   ```bash
   pymodaq-actor --plugin pymodaq_plugins_andor.daq_2Dviewer_andor.DAQ_2DViewer_Andor \
                 --name andor_camera --host localhost
   ```

3. **Dashboard integration:** deferred to Phase 2.

4. **Serialization:** `DataToExport` published via `DataPublisher.send_data` using binary
   payload (`serializall`). The `_last_data` cache is updated on every `read_publish` call
   and on every `query_data(fresh=True)` call.

5. **Settings broadcast:** `_director_registry: set[str]`, extended via
   `subscribe_director` / `unsubscribe_director`. On `set_info`, broadcasts XML settings
   to all registered directors via `set_director_settings` RPC.

**What this solves immediately:** a user with a spectrometer that also has a motorized
wavelength drive can run:
```bash
pymodaq-actor --plugin MySpectrometer --name spec
```
Then in the Dashboard, add a `DAQ_Viewer LECODirector` targeting `spec` for the spectrum,
and a `DAQ_Move LECODirector` targeting `spec` for the wavelength. Both directors send RPCs;
the actor processes them sequentially in its event loop. No thread contention, no master/slave.

**Does not require:** any changes to existing `DAQ_Move`, `DAQ_Viewer`, `ActorListener`,
or any hardware plugin.

**Tests:** ✅
- `tests/utils/leco/test_pymodaq_actor.py` — 68 pure-Python tests, all pass
- No Qt, no real hardware required

---

## Phase 2 — Director refactor and legacy transition

**Goal:** Replace the "fake plugin" LECO model with a proper director layer. Deprecate
`ActorListener`/`ActorHandler` while keeping the old path functional via a config flag.

### Phase 2a — New director utility classes ✅ COMPLETE

**Deliverables:**

1. **`PymodaqActorMethods`** enum in `rpc_method_definitions.py` ✅ — `QUERY_DATA`,
   `CHANGE_TO`, `GET_CAPABILITIES`, `SUBSCRIBE_DIRECTOR`, `UNSUBSCRIBE_DIRECTOR`.

2. **`PymodaqDirector(GenericDirector)`** base class in `director_utils.py` ✅ — pure RPC
   wrapper with `query_data()`, `get_capabilities()`, `subscribe_settings()`,
   `unsubscribe_settings()`. No Qt dependency.

3. **`PymodaqMoveDirector(PymodaqDirector)`** ✅ — adds `change_to(name, value)`.

4. **`PymodaqDetectorDirector(PymodaqDirector)`** ✅ — detector subclass; data arrives
   via ZMQ subscription at the `DAQ_xDViewer_LECODirector` level (not here).

5. **Tests:** `tests/utils/leco/test_pymodaq_directors.py` — 11 pure-Python tests, all pass.
   Conftest extended to load `rpc_method_definitions.py` and `director_utils.py` directly.

**Note:** existing `ActuatorDirector` / `DetectorDirector` are kept unchanged alongside the
new classes. The new directors are additive — no existing code is removed or broken.

### Phase 2b — Rewire existing LECO plugins ✅ COMPLETE (Dashboard deferred)

**Deliverables:**

1. **`PymodaqMoveDirector`** and **`PymodaqDetectorDirector`** wired into
   `DAQ_Move_LECODirector` and `DAQ_xDViewer_LECODirector` respectively, replacing
   `ActuatorDirector` / `DetectorDirector` internally. ✅

2. **`LECODirector` mixin** updated: `use_legacy_actor=False` → `PymodaqDataListener`;
   `True` → `PymodaqListener`. ✅

3. **Compatibility shim:** `ActorListener` / `ActorHandler` marked `@deprecated` in
   docstrings. Config flag `use_legacy_actor` (default `true` during transition):
   - `use_legacy_actor = true` → old `ActorListener`-based flow, unchanged
   - `use_legacy_actor = false` → expects a `PymodaqActor` on the other end ✅

4. **Settings sync:** directors call `subscribe_director` on `ini_stage` /
   `ini_detector`, and `unsubscribe_director` on `close`. ✅

5. **`pymodaq-actor` CLI entry point** registered in `pyproject.toml`. ✅

6. **Bug fixes applied during implementation:**
   - `change_to` auto-publishes after writing (actor side) so directors receive the
     updated value on the ZMQ channel without waiting for the next polling tick. ✅
   - `ini_stage` / `ini_detector` request initial position/frame immediately after
     subscribing to the ZMQ data channel. ✅
   - ZMQ subscription uses the actor's full name (`namespace.component`) not just
     the component name, fixing a topic-prefix mismatch that silently dropped all
     published messages. ✅

7. **Dashboard integration for actors:** a "Start Actor" entry in the Dashboard menu
   that launches a `PymodaqActor` subprocess for a selected plugin. *(deferred)*

8. **Architecture doc** (`README_LECO_ACTOR.md`): RPC vs ZMQ channel explained with
   message-flow diagrams. ✅

**Tests:**
- `tests/utils/leco/test_pymodaq_actor.py` — 68 tests ✅
- `tests/utils/leco/test_pymodaq_directors.py` — 11 tests ✅
- `tests/utils/leco/test_leco_integration.py` — 16 tests ✅ (95 total)

---

## Phase 3 — Settings-as-DAQ: any parameter as an instrument axis

**Conceptual framing:** every entry in an actor's settings tree is already a readable
value; if it is also writable, it is a valid actuator axis. There is no fundamental
difference between a hardware position and a laser power setpoint living in the settings
tree — both are read via `get_parameters` RPC and written via `set_info` RPC. The
`Capabilities` declaration is the structured contract that makes this explicit.

- **Any `Observable` (or `Variable`) in the tree → readable → candidate DAQ_Viewer source.**
- **Any `Variable` in the tree → readable + writable → candidate DAQ_Move axis.**

The type of variable determines move-done semantics:
- `ContinuousVariable` (numeric): poll `get_parameters` until `|actual - setpoint| ≤ epsilon`.
- `DiscreteVariable` (enum): poll until `actual == setpoint` (exact match).
- Pure settings parameter (no physical feedback): epsilon = 0 → move-done on the
  first readback after the write, typically in < 1 RPC round-trip.

Plugin class per role:
- `DAQ_Move_SettingsAxis` — drives one `Variable` per module instance. *(Phase 3a)*
- `DAQ_0DViewer_SettingsParam` — reads one `Observable` per module instance. *(Phase 3b)*

Both are thin wrappers (≈ 50 lines each) shipped as part of pymodaq, not separate
plugin packages. Batching multiple variables per module instance (e.g. heater power +
setpoint) is deferred to a later phase; the `change_to(name: list, value: list)` API
already supports it on the actor side.

**Goal (Phase 3a):** `DAQ_Move_SettingsAxis` — any scalar `Variable` in the actor's
settings tree becomes a `DAQ_Move` axis without writing a new plugin file.

**Deliverables (Phase 3a):**

1. **`SettingsAxisDirector(PymodaqMoveDirector)`** — targets a `(actor_name, param_path)`
   pair expressed as a `Variable` name:
   - `change_to(name, pos)` → `set_info(param_path, pos)` RPC
   - `query_data(fresh=True)` → `get_parameters([param_path])` RPC (move-done poll)
   - Units/bounds/epsilon populated from the `Variable` declaration; falls back to the
     actor's Parameter tree limits for plugins without declared `Capabilities`
   - No ZMQ subscription — pure RPC, consistent with Director/Spectator invariant

2. **`DAQ_Move_SettingsAxis`** — minimal `DAQ_Move_base` subclass wrapping
   `SettingsAxisDirector`. Appears in the instrument list as `"SettingsAxis (LECO)"`.

3. **UI flow:** when `DAQ_Move_SettingsAxis` is selected in the Dashboard:
   - User enters the actor name
   - Dialog calls `get_capabilities()`, filtered to `Variable`s
   - User picks a variable from the list
   - Plugin self-configures (units, bounds, step) from the `Variable` metadata
   - No other plugin file needed, no code to write

**Deliverables (Phase 3b):**

4. **`DAQ_0DViewer_SettingsParam`** — minimal `DAQ_Viewer_base` subclass that reads one
   `Observable` from the actor's settings tree via `get_parameters` RPC.  No ZMQ
   subscription — polling only, consistent with Director/Spectator invariant.
   Appears in the instrument list as `"SettingsParam (LECO)"`.

---

## Phase 4 — Spectator

**Goal:** A lightweight, read-only data consumer that subscribes to one or more actors'
data channels, without any control responsibility. Eventual replacement for the DataMixer
substrate and the data-reception half currently embedded in `DAQ_xDViewer_LECODirector`.

**Note on infrastructure:** pyleco's `Listener` + `DataSubscriberHandler` already
implement the ZMQ SUB channel in a dedicated thread. A Spectator does **not** need to
build custom ZMQ handling — it wraps the existing `PymodaqDataListener` (which already
uses `DataSubscriberHandler`). The only new work is the **bounded-queue signal bridge**
between the listener thread and the Qt display thread.

**Deliverables:**

1. **`SpectatorSubscriber`** — thin wrapper around `PymodaqDataListener` that adds a
   **bounded Qt signal queue (depth 1)**: when a new `DataToExport` frame arrives before
   the previous one has been shown, the old frame is replaced. Emits
   `data_received(str, DataToExport)` into the Qt main thread. Sends no RPC commands.
   - `subscribe(actor_name)` / `unsubscribe(actor_name)` delegate to `DataSubscriberHandler`
   - Can subscribe to multiple actors simultaneously
   - Maintains `_cache: dict[actor_name, DataToExport]` for sync modes
   - Does **not** need a Coordinator connection if used purely for data reception

2. **`DAQ_xDViewer_LECODirector` audit / rewire (Phase 4a):** verify that the existing
   `PymodaqDataListener` runs in a thread fully independent of the RPC control path. If the
   current implementation shares a Qt signal queue between data and control events, rewire
   to give the data listener its own bounded-queue path. The director retains only its
   `PymodaqDetectorDirector` (RPC control). This completes the full Director/Spectator
   separation for the viewer plugin.

3. **`SpectatorWidget(QWidget)`** — hosts `SpectatorSubscriber` in a `QThread`. Routes
   incoming data to `viewer_factory`. Provides:
   - Actor subscription management UI (add/remove actors)
   - Sync mode selector (`latest` / `barrier` / `timestamp` with configurable window)
   - Optional formula/processing step (identical in concept to DataMixer's formula console)

4. **Dashboard integration:** "Add Spectator" alongside "Add Detector" and "Add Actuator".
   Creates a `SpectatorWidget` docked in the Dashboard area.

5. **DataMixer refactor** (separate sub-task): refactor `DataMixerGUI` to use
   `SpectatorSubscriber` for its live-sync path, retiring `LiveSyncWorker`'s direct HDF5
   polling in favour of actor data subscription. The HDF5 replay path is kept for offline use.

---

## File-level change summary

### New files
```
pymodaq/control_modules/capabilities.py            # Observable, Variable, Capabilities,
                                                   # infer_capabilities  (Phase 0)
pymodaq/utils/leco/actor.py                        # PymodaqActor, actor_main CLI  (Phase 1)
pymodaq/control_modules/daq_move_settings_axis.py  # DAQ_Move_SettingsAxis  (Phase 3)
pymodaq/utils/leco/spectator.py                    # SpectatorSubscriber  (Phase 4)
pymodaq/gui/spectator_widget.py                    # SpectatorWidget  (Phase 4)
```

### Modified files
```
pymodaq/utils/leco/director_utils.py               # PymodaqDirector base +
                                                   # PymodaqMoveDirector,
                                                   # PymodaqDetectorDirector  ✅ Phase 2a
pymodaq/utils/leco/rpc_method_definitions.py       # PymodaqActorMethods enum  ✅ Phase 2a
pymodaq/utils/leco/leco_director.py                # use new directors  (Phase 2b)
pymodaq/utils/leco/daq_move_LECODirector.py        # rewire internals  (Phase 2b)
pymodaq/utils/leco/daq_xDviewer_LECODirector.py    # rewire internals  (Phase 2b)
pymodaq/utils/leco/pymodaq_listener.py             # deprecation markers  (Phase 2b)
pyproject.toml                                     # new CLI entry point pymodaq-actor  (Phase 1)
```

---

## Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Observable/Variable location | `pymodaq/control_modules/capabilities.py` | Hardware-capability concern; plugin authors already import from `pymodaq.control_modules`; cannot go in `pymodaq_data` (wrong layer) |
| Observable/Variable callable getters | No (metadata only) | Not serializable over LECO; duplicates existing reading mechanisms; couples metadata to live plugin instance |
| Variable hierarchy | `Variable` (base) / `ContinuousVariable` (lo/hi/epsilon) / `DiscreteVariable` (choices) | Continuous ranges and discrete enumerations are fundamentally different constraint models; epsilon (move-done tolerance) is meaningful only on actuators, not on string/enum settings |
| `Observable.shape` | `tuple[int \| None, ...]` | `None` in a dimension means variable-length (e.g. event-list detectors); JSON-safe (`null`) |
| `"kind"` discriminator | On Variable subclasses in `to_dict` / `from_dict` | Needed to round-trip subclass identity through JSON; `Observable` has no discriminator (only one class) |
| `infer_capabilities` produces | `ContinuousVariable` (not `Variable`) for actuator axes | `_epsilons` maps to `epsilon` on `ContinuousVariable`; axes are always continuous |
| `query_data` plural/singular | Accept `str \| list \| None`; normalize str → `[str]` | Callers should not need to wrap a single name in a list; no-op for existing list callers |
| `change_to` plural | Accept `str \| list` + matching `value`; iterate `zip` for lists | Single RPC call to write multiple variables; backward-compatible (single str still works) |
| `get_actuator_value` maps to | `query_data(fresh=True)` | Must poll real hardware position to detect motion completion; a cached value would give a false move-done signal |
| Settings conflict resolution | Last-write-wins | Sufficient for v1; explicit conflict arbitration deferred |
| Actor launch (Phase 1) | CLI only (`pymodaq-actor`) | Keeps Phase 1 risk-free; Dashboard "Start Actor" button added in Phase 2 |
| Old LECO path | Compatibility shim via `leco.use_legacy_actor` flag | Both paths coexist during transition; old path removed once all plugins migrate |
| Plugin update burden | Opt-in `capabilities` declaration; `infer_capabilities` fallback | Existing plugins need zero changes; new plugins opt in for richer director UI |
| Spectator data access | ZMQ SUB only via pyleco `DataSubscriberHandler`, no `query_data` RPC | Spectators are passive; pyleco already provides the SUB socket infrastructure in `ExtendedMessageHandler`; SpectatorSubscriber only adds bounded-queue bridging to Qt |
| Multi-actor sync | Three modes: `latest`, `barrier`, `timestamp` | Different use cases need different strategies; selectable in `SpectatorWidget` |
| Spectator vs DataMixer | Spectator replaces DataMixer's live-sync substrate; HDF5 replay kept | DataMixer becomes a `SpectatorWidget` with formula evaluation on top |
| Director/Spectator strict separation | Directors: RPC only. Spectators: ZMQ SUB only. Never mixed. | A burst of data frames must never block `stop_grab`/`stop` RPCs; operator must always retain control of running hardware |
| Spectator backpressure | Bounded queue depth 1: new frame replaces unprocessed old frame | Prevents unbounded queue growth when display is slower than data rate; control path is never affected |
| Move-done for settings params | Poll `get_parameters` RPC until `\|actual − setpoint\| ≤ epsilon`; epsilon = 0 for pure settings | Same code path as physical actuators; instantaneous for config registers, toleranced for real hardware |
| Settings-as-DAQ plugin classes | New thin plugins `DAQ_Move_SettingsAxis` + `DAQ_0DViewer_SettingsParam` | Separate classes keep concerns distinct; existing DAQ_Move/DAQ_Viewer unchanged; plugins are ≈ 50 lines each |
| Batch variable control | Deferred; single Variable per module instance for Phase 3 | `change_to(list, list)` already supported on actor; UI for multi-variable modules deferred |

---

## Open questions / deferred decisions

| # | Question | Deferred to |
|---|---|---|
| 1 | Multi-actor spectator: merge into one viewer or separate tabs per actor? | Phase 4 kickoff |
| 2 | DataMixer HDF5 replay: keep as separate tool or unified with SpectatorWidget? | Phase 4 kickoff |
| 3 | Settings conflict resolution beyond last-write-wins | Post-Phase 2 |
| 4 | When to remove `use_legacy_actor` shim and drop `ActorListener` entirely | After majority of plugins have migrated |
| 5 | ~~Audit `DAQ_xDViewer_LECODirector` (Phase 2b): does the current `PymodaqDataListener` run in a thread fully independent of the RPC control path, or do they share a queue? If shared, the Phase 4a rewire (SpectatorSubscriber) is a bug-fix, not just a refactor.~~ **CLOSED (Phase 4a complete):** confirmed shared queue (`cmd_signal`). Fixed by adding `data_signal = Signal(str, object)` to `ListenerSignals`; `DataSubscriberHandler.handle_subscription_message` now emits `data_signal(topic, dte)` instead of a `ThreadCommand` on `cmd_signal`. Both director plugins connect to `data_signal`. ZMQ data frames can no longer block control commands in the Qt event queue. Full `SpectatorSubscriber` thread remains a future enhancement (Phase 4), not a correctness requirement. | ~~Before Phase 4a~~ Complete |
| 6 | Batch variable control: when a `DAQ_Move_SettingsAxis` should drive multiple variables simultaneously (e.g. heater power + setpoint), is this a second plugin type or a configuration of the same one? | Phase 3 kickoff |

---

## Dependency and sequencing

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3
                    └──────────────► Phase 4  (can start in parallel after Phase 1)
```

Phase 0 and Phase 1 are entirely additive — zero risk to existing functionality. Phase 2 is
the only phase with deprecation impact and should go through a longer review cycle. Phase 3
and Phase 4 are additive on top of Phase 2.
