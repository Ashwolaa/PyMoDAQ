# Plan: PymodaqActor GUI (`actor_gui.py`)

---

## Open Issues & Design Decisions

The following issues were identified during plan review. Sections marked **RESOLVED** have been
updated in the plan body; **SUPERSEDED** means the design has changed making the issue moot;
**DEFERRED** are tracked but not yet implemented.

### Issue 1 — `create_load_daq_viewer` has no `grabber_type` parameter — RESOLVED
Actual signature is `create_load_daq_viewer() -> tuple[SharedUI, DAQ_Viewer]` with no args.
Grabber type is set after creation via `daq_viewer.detector = SelectedModule(DAQTypesEnum[det_type], detector)`.

### Issue 2 — `instruments.py` raises on import when no plugins installed — SUPERSEDED
The actor GUI no longer imports `instruments.py` or uses `ACTUATOR_TYPES`/`DET_TYPES`.
Hardware discovery uses `pymodaq.hardware` entry points instead (see Plugin Discovery below).

### Issue 3 — `init_instrument` only updates settings — RESOLVED
Merged `init_instrument` + `start_actor` into a single `init_instrument(plugin_class, actor_name, host, port)` slot.
"Init Instrument" is the single action button: instantiates the device class, opens hardware, registers with coordinator, starts listening.
"Start Actor" button removed. Selecting hardware only previews capabilities (no hardware touched).

### Issue 4 — `notify_directors` / `NOTIFY_EVENT` scope — DEFERRED
Useful for pushing actor state changes to remote directors but not needed for `actor_gui.py` itself.
Deferred to a separate PR.

### Issue 5 — Settings pre-filling uses wrong access pattern — RESOLVED
Use `settings.child('actor_name').setValue(...)`, not `settings['actor_name']`.

### Issue 6 — LED widget class not specified — RESOLVED
Use `pymodaq_gui.utils.widgets.qled.QLED`.

### Issue 7 — `ActorState` usage unclear — RESOLVED
State is tracked exclusively via `ThreadCommand` values through `status_sig`.

### Issue 8 — `plugin_type` naming inconsistency — SUPERSEDED
`plugin_type` / `plugin_name` removed entirely; replaced by a single `instrument` selector.

### Issue 9 — `closeEvent` thread cleanup — RESOLVED
`closeEvent` uses `QMetaObject.invokeMethod` with `BlockingQueuedConnection` then
`thread.quit(); thread.wait()`.

### Issue 10 — `pymodaq.hardware` entry point group is new — OPEN
No existing plugin packages register it yet. The list will be empty without dev installs.
Provide a clear empty-state message; consider shipping `MockStageDevice` as a built-in
fallback for development / testing.

---

## Instrument Loading Design

The actor GUI picks a **hardware instrument class** directly, bypassing the DAQ plugin layer.
Instrument classes implement the actor device interface:

```
connect()                                    — open hardware
close()                                      — close hardware (called by PymodaqActor.disconnect)
read(names: list[str] | None = None) -> DataToExport
write(name: str, value: Any) -> None
capabilities  [optional]  -> Capabilities   — if absent, infer_capabilities() is used
```

Hardware init happens entirely on the actor side:
- `PymodaqActor.connect()` calls `device_class()` then `device.connect()`.
- `PymodaqActor.disconnect()` calls `device.close()`.
- `ini_stage()` / `ini_detector()` are **never** called from the actor side; those belong to
  `DAQ_Move_LECODirector` / `DAQ_xDViewer_LECODirector` when they connect as directors.

The actor GUI's **"Init Instrument"** button records the class and sets the Instrument LED green.
The **"Start Actor"** button passes the class to `PymodaqActor`. Init_instrument should initialize the hardware similarly to `DAQ_Move` / `DAQ_Viewer` as currently implemented in start_actor.

Selecting a plugin should update the settings tree with the plugin's parameters.
Init instrument should start the actor and initialize the hardware.
Deinit instrument should stop the actor and close the hardware.


---

## Context

PyMoDAQ currently uses `DAQ_Move` / `DAQ_Viewer` as actors over TCP. The new LECO actor path
(`PymodaqActor`) is more general: a single actor can expose **both** variables (actuator axes)
and observables (detector outputs) simultaneously. `Capabilities` already separates them.
For example, a camera actor could expose `exposure_time` as a variable (→ `DAQ_Move` director)
and `frame` as an observable (→ `DAQ_Viewer` director), all from one actor.

This GUI makes the new path accessible without writing Python code. It runs on the **acquisition
computer** (hardware side). Directors run on the dashboard computer.

---

## Key Design: Capabilities Tree as Central UI

After the user selects an instrument (or after the actor starts), the GUI shows a capability tree:

```
instrument: MockStageDevice
├── Variables
│   └── position  [float, -100 … 100, ε=0.001 mm]   [Open DAQ_Move ▶]
└── Observables
    └── (none)
```

Capabilities are shown **before** the actor starts (preview from `cls.capabilities` /
`infer_capabilities`) so the user can confirm what will be exposed.
After `ACTOR_READY` the tree is refreshed with live data from `actor.get_capabilities()`.

Each row has an action button that opens a pre-configured `DAQ_Move_LECODirector` (for variables)
or `DAQ_xDViewer_LECODirector` (for observables), pointing at `localhost` with `actor_name` and
`use_legacy_actor=False` pre-filled.

An **"Auto-open all directors"** checkbox opens all directors automatically on `ACTOR_READY`.

---

## Plugin Discovery

Hardware classes are discovered via the `pymodaq.hardware` entry point group.
Plugin packages declare pure hardware classes (no DAQ wrapper required):

```toml
# In a plugin package's pyproject.toml
[project.entry-points."pymodaq.hardware"]
MockStage = "pymodaq_plugins_mock.hardware.mock_stage:MockStageDevice"
Andor     = "pymodaq_plugins_andor.hardware.ccd:AndorCCDDevice"
```

A new `hardware_registry.py` module builds the registry at import time:

```python
# pymodaq/utils/leco/hardware_registry.py
from importlib.metadata import entry_points
from pymodaq.control_modules.capabilities import infer_capabilities

def get_hardware_registry() -> list[dict]:
    """Return [{name, cls, capabilities}] from pymodaq.hardware entry points."""
    result = []
    for ep in entry_points(group='pymodaq.hardware'):
        try:
            cls = ep.load()
            caps = getattr(cls, 'capabilities', None)
            if caps is None:
                caps = infer_capabilities(cls())
            result.append({'name': ep.name, 'cls': cls, 'capabilities': caps})
        except Exception:
            logger.warning("Could not load hardware entry point %r: %s", ep.name, exc)
    return result

# Module-level registry (loaded once at import; empty if no hardware registered)
HARDWARE_REGISTRY: list[dict] = get_hardware_registry()
HARDWARE_NAMES: list[str] = [e['name'] for e in HARDWARE_REGISTRY]
```

Fallback: if `HARDWARE_REGISTRY` is empty the instrument list is empty and the status bar shows
*"No hardware classes registered — install a plugin package that uses pymodaq.hardware entry points."*

---

## Architecture

```
PymodaqActorGUI (CustomApp, ParameterManager)
│
├── LECO dock
│   ├── params: actor_name, host, port
│   ├── params: instrument (single flat list of hardware class names)
│   ├── params: auto_open_all (bool, default False)
│   ├── LEDs: Instrument / Coordinator / Actor
│   └── toolbar: [Init Instrument] [Start Actor] [Stop Actor]
│
├── Capabilities dock  (shown on instrument select; refreshed on ACTOR_READY)
│   └── ParameterTree built from Capabilities
│       Variables group   → each: properties + [Open DAQ_Move ▶] action
│       Observables group → each: properties + [Open DAQ_Viewer ▶] action
│
└── Status bar
```

Backend thread model:
```
QThread: ActorWorkerThread
└── ActorWorker(QObject)
    ├── _plugin_class  (hardware class, set by init_instrument)
    ├── PymodaqActor   (wraps class; actor.listen() runs in daemon thread)
    └── status_sig = Signal(ThreadCommand)
```

Worker → GUI ThreadCommands:
| Command         | Attribute    | Meaning                                      |
|---|---|---|
| INSTRUMENT_INIT | class        | Class validated; Instrument LED → green      |
| ACTOR_READY     | Capabilities | Actor up; capabilities refreshed in tree     |
| ACTOR_STOPPED   | —            | Actor shut down cleanly                      |
| UPDATE_STATUS   | str          | Status bar text                              |
| ERROR           | str          | Error message; Instrument LED → red          |

---

## `PymodaqActorGUI` params

```python
params = [
    {'title': 'Actor name:', 'name': 'actor_name', 'type': 'str', 'value': 'actor'},
    {'title': 'Host:',       'name': 'host',       'type': 'str', 'value': 'localhost'},
    {'title': 'Port:',       'name': 'port',       'type': 'int', 'value': COORDINATOR_PORT},
    {'title': 'Instrument:', 'name': 'instrument', 'type': 'list',
     'limits': HARDWARE_NAMES},    # populated from pymodaq.hardware entry points
    {'title': 'Auto-open directors:', 'name': 'auto_open_all', 'type': 'bool', 'value': False,
     'tip': 'Open a director window for every capability when actor starts'},
]
```

`value_changed`:
- `instrument` → `_on_instrument_selected()`: load class from `HARDWARE_REGISTRY`,
  store as `self._plugin_class`, call `_populate_caps_tree(entry['capabilities'])`,
  show Capabilities dock as a preview.

---

## GUI Lifecycle / Button States

| State           | Instr. | Coord. | Actor | Init | Start | Stop | Caps tree         |
|---|---|---|---|---|---|---|---|
| Initial         | grey   | grey   | grey  | ✓    | ✗     | ✗    | preview (if list non-empty) |
| Instrument OK   | green  | grey   | grey  | ✓    | ✓     | ✗    | preview           |
| Actor READY     | green  | green  | green | ✗    | ✗     | ✓    | live (refreshed)  |
| Actor stopped   | green  | grey   | grey  | ✓    | ✓     | ✗    | preview           |
| Error           | red    | *      | grey  | ✓    | ✗     | ✗    | unchanged         |

---

## Files to Create / Modify

### New: `packages/pymodaq/src/pymodaq/utils/leco/hardware_registry.py`
`get_hardware_registry()` + `HARDWARE_REGISTRY` + `HARDWARE_NAMES`.

### Modified: `packages/pymodaq/src/pymodaq/utils/leco/actor_gui.py`
- Remove `ACTUATOR_TYPES`, `DET_TYPES`, `ACTUATOR_NAMES` imports and all uses.
- Import `HARDWARE_REGISTRY`, `HARDWARE_NAMES` from `hardware_registry`.
- Replace `plugin_type` / `plugin_name` params with single `instrument` param.
- Replace `_update_plugin_name_limits()` / `_load_plugin_for_display()` with
  `_on_instrument_selected()`.
- Show Capabilities dock on instrument selection (preview), not only on `ACTOR_READY`.

### Modified: `packages/pymodaq/tests/utils/leco/test_actor_gui.py`
- Replace mocks for `ACTUATOR_TYPES`/`DET_TYPES`/`ACTUATOR_NAMES` with mock for
  `HARDWARE_REGISTRY` / `HARDWARE_NAMES`.
- Update `TestLoadPluginClass` → `TestHardwareRegistry` testing `get_hardware_registry`.
- Update GUI fixtures to patch `HARDWARE_REGISTRY`.

### Modified: `packages/pymodaq/tests/utils/leco/conftest.py`
- Load `hardware_registry.py` via `_load_module_from_path`.

### Already done: `packages/pymodaq/pyproject.toml`
Entry point `pymodaq-actor-gui = "pymodaq.utils.leco.actor_gui:main"` ✓

### Already done: `packages/pymodaq/src/pymodaq/utils/leco/actor.py`
`connect()` → calls `device.connect()` after instantiation;
`disconnect()` → calls `device.close()` instead of `device.adapter.close()` ✓

---

## Director Window Pre-configuration

Same as before — director windows use `DAQ_Move_LECODirector` / `DAQ_xDViewer_LECODirector`:

```python
# Variable → DAQ_Move_LECODirector
shared_ui, daq_move = create_load_daq_move('Simple')
daq_move.actuator = 'LECODirector'
try:
    daq_move.settings.child('move_settings', 'actor_name').setValue(actor_name)
    daq_move.settings.child('move_settings', 'host').setValue(host)
    daq_move.settings.child('move_settings', 'use_legacy_actor').setValue(False)
except Exception:
    logger.warning('Could not pre-fill move director settings')
shared_ui.show()

# Observable → DAQ_xDViewer_LECODirector (dim inferred from obs.shape)
ndim = len(obs.shape)
det_type = {1: 'DAQ0D', 2: 'DAQ1D', 3: 'DAQ2D'}.get(ndim, 'DAQ0D')
shared_ui, daq_viewer = create_load_daq_viewer()
daq_viewer.detector = SelectedModule(DAQTypesEnum[det_type], 'LECODirector')
shared_ui.show()
```

---

## Implementation Status

| File | Status |
|---|---|
| `actor.py` — `connect()` / `disconnect()` overrides | **Done** |
| `hardware_registry.py` | **Done** — new file |
| `actor_gui.py` — instrument list replaces plugin_type/name | **Done** |
| `test_actor_gui.py` — update mocks | **Done** |
| `conftest.py` — load `hardware_registry` + qtpy stubs | **Done** |

---

## Verification

```bash
# 1. Headless unit tests (should all still pass after refactor)
QT_QPA_PLATFORM=offscreen python3 -m pytest \
  packages/pymodaq/tests/utils/leco/test_actor_gui.py -v

# 2. GUI smoke test (empty list expected until a hardware package is installed)
python3 -m pymodaq.utils.leco.actor_gui
# → Instrument list empty but GUI opens cleanly
# → Install/register MockStageDevice; restart → "MockStage" appears in list
# → Select → Capabilities dock shows preview
# → Init + Start Actor → Live capabilities refreshed
# → [Open DAQ_Move ▶] → director window opens pre-filled

# 3. Integration (coordinator + proxy running)
# → Start actor; verify director auto-opens if checkbox set
# → Verify move_abs from director; verify data published on ZMQ channel
```
