# Plan — LECO Network Manager GUI

## Motivation

When developing and debugging a LECO-based PyMoDAQ session, several recurring pain points arise:

- **Stale actors**: a process crashed or was killed without signing out; the coordinator still
  has the component registered, causing `RECEIVER_UNKNOWN` errors on the next run.
- **No overview**: it is not obvious which actors are live, what they expose, or which directors
  are connected to which actor.
- **Manual startup**: coordinator and proxy must be started from a terminal before PyMoDAQ;
  there is no integrated launcher.
- **Multiple proxies**: advanced setups (high-speed cameras on a dedicated proxy) have no
  management UI.

The LECO Network Manager addresses all of the above in a single window.

---

## Decision log

| Question | Decision | Rationale |
|---|---|---|
| Integration format | `CustomApp` (standalone), not `CustomExt` | This is infrastructure management, not a DAQ workflow. No need for `ModulesManager` or scan context. Can still be launched from the dashboard toolbar. |
| Discovery API | `CoordinatorDirector.get_local_components()` + `get_role()` RPC | `get_local_components()` returns all signed-in names; `get_role()` classifies each one without guessing. |
| Refresh strategy | Two-tier polling | Fast poll (1–2 s): component list only (lightweight). Slow poll (5 s): per-actor details. Immediate detail fetch on list change. pyleco coordinator has no push notifications. |
| Director names | User-configurable; default `f"{role}_{uuid4().hex[:6]}"` | Current `random.randrange` default is not reproducible. Replace with short UUID so two instances never collide and the name is stable across restarts if user sets it. |
| IP tracking | Embed host in `get_role()` response | `get_local_components()` returns only names. `get_role()` returns a dict `{"role": ..., "host": ...}` so the manager sees source IP without extra calls. |
| Shutdown | `shutdown()` RPC on actors; `disconnect()` RPC on directors | Solves stale-registration bug. Manager sends RPC; component cleans up and signs out. |
| Director rerouting | Deferred (Phase 4) | Needs `connect_to_actor(name)` RPC on `LECODirector`. Design is clear but not needed for v1. |
| Multiple proxies | Each proxy is a `ProxyRecord` with its own port pair | Manager can start/stop N proxies independently. |

---

## Component naming

### Directors (current → new)

**Current** (`leco_director.py:68`):
```python
name = f'{self._title}_{random.randrange(0, 10000)}_director'
```

**New**: add `director_name` parameter to `leco_parameters`:
```python
{'title': 'Director name:', 'name': 'director_name', 'type': 'str',
 'value': '',
 'tip': 'Leave blank for auto-generated name (uuid-based). Set explicitly for stable identity.'}
```

At init time in `LECODirector.__init__`:
```python
configured = self.settings['director_name'].strip()
if configured:
    name = configured
else:
    role = 'move' if isinstance(self, DAQ_Move_base) else 'viewer'
    name = f"{role}_dir_{uuid4().hex[:6]}"
```

This name is stable if the user sets it, and collision-free otherwise.

---

## `get_role()` response contract

All LECO-aware components implement `get_role()`. 
An enum is used to define the role of the component.
class LECORole(StrEnum):
    ACTOR = "actor"
    DIRECTOR = "director"
    COORDINATOR = "coordinator"
    SPECTATOR = "spectator"
The return value is a plain dict so it
is forward-compatible:

```python
# Actor
{"role": LECORole.ACTOR, "host": communicator.socket.getsockopt_string(zmq.LAST_ENDPOINT)}

# Director
{"role": LECORole.DIRECTOR, "host": socket.gethostname()}

# Future: spectator
{"role": LECORole.SPECTATOR, "host": ...}
```

The manager calls `get_role(timeout=0.3)` on every component name returned by
`get_local_components()`. Components that do not respond within the timeout are classified
`"unknown"` and shown as potentially stale.

---

## Data model (`leco_manager.py`, no Qt)

```python
@dataclass
class ComponentRecord:
    name: str               # short name, e.g. "stage"
    full_name: str          # namespace-qualified, e.g. "localhost.stage"
    role: str               # "actor" | "director" | "coordinator" | "unknown"
    host: str | None        # source IP / hostname from get_role()
    # actor-only:
    capabilities: Capabilities | None = None
    grabbed_names: list[str] | None = None
    pub_topic: str | None = None
    # state:
    last_seen: datetime = field(default_factory=datetime.now)
    reachable: bool = True

@dataclass
class ProxyRecord:
    in_port: int            # publisher side (actors publish here)
    out_port: int           # subscriber side (directors subscribe here)
    label: str = ""         # user-friendly label, e.g. "cameras"
    process: Popen | None = None   # None = externally managed
    alive: bool = False

@dataclass
class CoordinatorRecord:
    host: str
    port: int
    namespace: str | None = None
    nodes: dict[str, str] = field(default_factory=dict)
    process: Popen | None = None
    alive: bool = False
```

`LECONetworkMonitor` class (owns a `CoordinatorDirector`):

| Method | Description |
|---|---|
| `connect(host, port)` | Create `CoordinatorDirector`, test reachability |
| `refresh_components()` | `get_local_components()` → call `get_role()` on each new name |
| `refresh_actor_details(name)` | Fetch capabilities, grabbed_names, pub_topic in one pass |
| `shutdown_component(name)` | RPC `shutdown()` to actor or `disconnect()` to director |
| `start_coordinator(host, port, namespace)` | `subprocess.Popen` |
| `stop_coordinator()` | `proc.terminate()` + wait |
| `add_proxy(in_port, out_port, label)` | `subprocess.Popen`, append `ProxyRecord` |
| `remove_proxy(in_port)` | `proc.terminate()`, remove record |
| `probe_proxy(in_port, out_port)` | Try ZMQ connect + RCVTIMEO probe; update `alive` |

Callbacks (plain callables; GUI layer wraps them as Qt signals):
- `on_components_changed(records: list[ComponentRecord])`
- `on_actor_details_changed(record: ComponentRecord)`
- `on_proxy_status_changed(record: ProxyRecord)`
- `on_coordinator_status_changed(record: CoordinatorRecord)`

---

## GUI layout (`manager_gui.py`)

```
┌──────────────────────────────────────────────────────────────┐
│  LECO Network Manager               [⟳ auto 2s ▾]  [⟳ now]  │
├──────────────────────────────────────────────────────────────┤
│  NETWORK                                                      │
│   Coordinator  ● lab @ localhost:12300   [Start ▾] [Stop]    │
│   Proxy #1  ●  in:11100  out:11099  cameras      [Stop] [✕]  │
│   Proxy #2  ○  in:11102  out:11101  (stopped)    [Start][✕]  │
│                                             [+ Add proxy...]  │
├──────────────────────────────────────────────────────────────┤
│  COMPONENTS                                                   │
│   Name           Role      Host          Status      [✕]     │
│ ▶ stage          actor     192.168.1.10  idle     1V  [✕]    │
│   └─ position  ContinuousVariable  lo=−50  hi=50  ε=0.01     │
│ ▶ cam            actor     192.168.1.10  grabbing 2O  [✕]    │
│   └─ frame     Observable  shape=(1024,1024)  dtype=uint16   │
│   └─ spectrum  Observable  shape=(2048,)      dtype=float32  │
│   move_dir       director  192.168.1.10  –      → stage      │
│   det_dir_1      director  192.168.1.11  –      → cam        │
│   det_dir_2      director  192.168.1.11  –      → cam        │
│   COORDINATOR    system    localhost     –                    │
│   ghost          unknown   –             no reply    [✕]     │
└──────────────────────────────────────────────────────────────┘
```

- `▶` row: click to expand inline capability detail
- `[✕]` on actor/director: calls `shutdown_component(name)` via RPC
- `[✕]` on unknown: removes from local display only (cannot send RPC; component may be dead)
- `[✕]` on proxy: calls `remove_proxy(in_port)` — terminates owned process or no-op if external
- `[Start ▾]` on coordinator: dropdown with host/port/namespace fields before launching

---

## Implementation phases

### Phase 0 — RPC additions (existing files)

**`rpc_method_definitions.py`**:
- Add `GET_ROLE`, `SHUTDOWN` to `PymodaqActorMethods`
- Add new `DirectorRPCMethods` enum with `GET_ROLE`, `DISCONNECT`

**`actor.py`**:
- `get_role() → dict` — `{"role": "actor", "host": ...}`
- `shutdown()` — stop continuous grab, unregister all directors, close device, signal listen loop

**`leco_director.py`**:
- Register `get_role` handler in listener → returns `{"role": "director", "host": ...}`
- Register `disconnect` handler → unsubscribe from actor, stop listener
- Add `director_name` to `leco_parameters` (see naming section above); replace `random` default

**Tests**: `test_pymodaq_actor.py` (add `get_role`, `shutdown` cases),
`test_leco_director.py` (add `get_role`, naming cases)

---

### Phase 1 — `leco_manager.py`

- `ComponentRecord`, `ProxyRecord`, `CoordinatorRecord` dataclasses
- `LECONetworkMonitor` class (no Qt)
- Two-tier poll loop: component list every 2 s, actor details every 5 s
- Subprocess management for coordinator and proxy

**Tests**: `test_leco_manager.py` — mock `CoordinatorDirector`, verify classification,
verify subprocess lifecycle, verify stale-detection (component disappears from list)

---

### Phase 2 — `manager_gui.py`

- `LECOManagerGUI(CustomApp)` — main window
- `NetworkPanel(QWidget)` — coordinator + proxy rows
- `ComponentsTable(QTreeWidget)` — sortable; actor rows expandable
- `AddProxyDialog(QDialog)` — in/out port spinboxes + label field
- Two `QTimer`s: fast (1 s component list), slow (5 s actor details)
- All `LECONetworkMonitor` callbacks wired to Qt signals in a thin adapter

**Tests**: `test_manager_gui.py` — Qt tests (skip headless); mock monitor

---

### Phase 3 — Entry point + dashboard integration

**`pyproject.toml`**:
```toml
leco-manager = "pymodaq.utils.leco.manager_gui:main"
```

**Dashboard toolbar** (`dashboard.py` or extension hook):
- Menu item "LECO Manager" → `LECOManagerGUI.show()`, reuse instance if already open

---

### Phase 4 — Director rerouting (future)

- Add `connect_to_actor(actor_name: str)` RPC to `LECODirector`
  - Unsubscribes from current actor, re-runs `ini_stage` / `ini_detector` against new actor
- Manager GUI: dropdown next to each director row; selecting a new actor sends the RPC
- No implementation timeline; architecture is compatible with Phase 0–3

---

## Open questions

- **Proxy alive detection**: ZMQ connect always "succeeds" even if nothing is there.
  Best approach: send a ZMQ SUB frame to the proxy out-port with a short `RCVTIMEO` and
  see if any frame arrives. Alternatively, if we own the process, `proc.poll() is None`
  is sufficient. Decision: use `proc.poll()` for owned proxies; flag external proxies as
  "unmonitored" unless user explicitly triggers a probe.

- **Multi-node**: `CoordinatorDirector.get_global_components()` returns `{node: [names]}`.
  Phase 1 targets single-node (`get_local_components()`). Multi-node display is a natural
  Phase 2 extension (group rows by node).

- **`get_role()` host field**: `zmq.LAST_ENDPOINT` gives the local bind address, not the
  remote client address. For the actor this is fine (it tells directors where to connect).
  For directors the useful IP is where the director process is running — `socket.gethostname()`
  or `socket.getsockname()`. To be confirmed during implementation.
