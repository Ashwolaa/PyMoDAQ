# Plan: PymodaqActor GUI (`actor_gui.py`)

## Context

PyMoDAQ currently uses `DAQ_Move` / `DAQ_Viewer` as actors over TCP. The new LECO actor path
(`PymodaqActor`) is more general: a single actor can expose **both** variables (actuator axes)
and observables (detector outputs) simultaneously. `Capabilities` already separates them.

This GUI makes the new path accessible without writing Python code. It runs on the **acquisition
computer** (hardware side). Directors run on the dashboard computer.

---

## Key Design: Capabilities Tree as Central UI

After the actor starts, the GUI fetches `get_capabilities()` and displays a tree:

```
actor: localhost.stage
├── Variables
│   ├── position  [float, -100 … 100, ε=0.001 mm]   [Start DAQ_Move ▶]
│   └── velocity  [float, 0 … 50]                    [Start DAQ_Move ▶]
└── Observables
    ├── frame     [2D, shape=(1024, 1024)]             [Start DAQ_Viewer ▶]
    └── spectrum  [1D, shape=(2048,)]                  [Start DAQ_Viewer ▶]
```

Each row has an action button that opens a pre-configured `DAQ_Move` (for variables) or `DAQ_Viewer`
(for observables), pointing at `localhost` with `actor_name` and `use_legacy_actor=False` pre-filled.

Multiple director windows can be open simultaneously for different capabilities.

An **"auto-open all"** checkbox in settings opens all directors automatically when the actor
reaches READY state.

---

## Implementation of the Capabilities Tree

Use PyMoDAQ's `Parameter` / `ParameterTree` system (consistent with the rest of the codebase):

```python
# Dynamically built from Capabilities after ACTOR_READY:
caps_params = [
    {'name': 'Variables', 'type': 'group', 'children': [
        {'name': 'position', 'type': 'group', 'children': [
            {'name': 'type',    'type': 'str',    'value': 'continuous', 'readonly': True},
            {'name': 'min',     'type': 'float',  'value': -100.0,       'readonly': True},
            {'name': 'max',     'type': 'float',  'value':  100.0,       'readonly': True},
            {'name': 'epsilon', 'type': 'float',  'value': 0.001,        'readonly': True},
            {'name': 'Open DAQ_Move', 'type': 'action'},
        ]},
        ...
    ]},
    {'name': 'Observables', 'type': 'group', 'children': [
        {'name': 'frame', 'type': 'group', 'children': [
            {'name': 'shape', 'type': 'str', 'value': '(1024, 1024)', 'readonly': True},
            {'name': 'Open DAQ_Viewer', 'type': 'action'},
        ]},
        ...
    ]},
]
```

Action parameters (`'type': 'action'`) render as buttons in the parameter tree.
`sigActivated` on each action → `_open_director_for(capability_name, capability_type)`.

---

## Architecture

```
PymodaqActorGUI (CustomApp, ParameterManager)
│
├── LECO dock
│   ├── params: actor_name, host, port
│   ├── params: plugin_type (list), plugin_name (list, populated on type change)
│   ├── params: auto_open_all (bool, default False)
│   ├── LEDs: instrument / coordinator / actor
│   └── toolbar: [Init Instrument] [Start Actor] [Stop Actor]
│
├── Capabilities dock
│   └── ParameterTree (built dynamically after ACTOR_READY)
│       Variables group  → each entry: properties + [Start DAQ_Move ▶] button
│       Observables group → each entry: properties + [Start DAQ_Viewer ▶] button
│
├── Settings dock
│   └── Plugin instance's settings_tree
│
└── Status bar
```

Backend thread model:
```
QThread: ActorWorkerThread
└── ActorWorker(QObject)
    ├── Plugin instance
    ├── PymodaqActor
    └── status_sig = Signal(ThreadCommand)
```

Worker → GUI ThreadCommands:
| Command         | Attribute          | Meaning                              |
|---|---|---|
| INSTRUMENT_INIT | bool               | Instrument init success/failure      |
| ACTOR_READY     | Capabilities       | Actor up; capabilities to display    |
| ACTOR_STOPPED   | —                  | Actor shut down cleanly              |
| UPDATE_STATUS   | str                | Status bar text                      |
| ERROR           | str                | Error message                        |

---

## GUI Lifecycle / Button States

| State           | Instr. | Coord. | Actor | Init | Start | Stop | Caps tree |
|---|---|---|---|---|---|---|---|
| Initial         | grey   | grey   | grey  | ✓    | ✗     | ✗    | hidden    |
| Instrument OK   | green  | grey   | grey  | ✓    | ✓     | ✗    | hidden    |
| Actor READY     | green  | green  | green | ✗    | ✗     | ✓    | populated |
| Actor stopped   | green  | grey   | grey  | ✗    | ✓     | ✗    | cleared   |
| Error           | red    | *      | grey  | ✓    | ✗     | ✗    | hidden    |

---

## Files to Create / Modify

### New: `packages/pymodaq/src/pymodaq/utils/leco/actor_gui.py`

**`ActorState(StrEnum)`**: `DISCONNECTED | READY | BUSY`

**`ActorWorker(QObject)`**
- `status_sig = Signal(ThreadCommand)`
- Slots (`QMetaObject.invokeMethod` / `Qt.QueuedConnection`):
  - `init_instrument(plugin_class, params_state=None)`
    → instantiate plugin → `ini_stage()` / `ini_detector()` → emit `INSTRUMENT_INIT(bool)`
  - `start_actor(name, host, port)`
    → `PymodaqActor(name, plugin_instance, host, port)` → `actor.listen(stop_event)` in sub-thread
    → emit `ACTOR_READY(capabilities)` or `ERROR`
  - `stop_actor()` → `stop_event.set()` → `actor.disconnect()` → emit `ACTOR_STOPPED`
  - `close_instrument()` → `plugin.close()`

**`PymodaqActorGUI(CustomApp, ParameterManager)`**

Main params (LECO dock):
```python
params = [
    {'name': 'actor_name',      'type': 'str',  'value': 'actor'},
    {'name': 'host',            'type': 'str',  'value': 'localhost'},
    {'name': 'port',            'type': 'int',  'value': COORDINATOR_PORT},
    {'name': 'plugin_type',     'type': 'list', 'limits': ['Actuator','Det 0D','Det 1D','Det 2D']},
    {'name': 'plugin_name',     'type': 'list', 'limits': []},
    {'name': 'auto_open_all',   'type': 'bool', 'value': False,
     'tip': 'Open a director window for every capability when actor starts'},
]
```

Key methods:
- `setup_docks()` → LECO dock + Capabilities dock (empty initially) + Settings dock
- `setup_actions()` → Init / Start / Stop toolbar buttons
- `connect_things()` → buttons → worker slots; `status_sig` → `_on_status`
- `_on_plugin_type_changed()` → repopulate plugin_name list
- `_on_plugin_selected()` → load plugin class; show its `settings_tree` in Settings dock
- `_on_status(cmd: ThreadCommand)` → update LEDs / buttons / status bar;
  if `ACTOR_READY`: call `_populate_caps_tree(caps)`, optionally `_open_all_directors(caps)`
- `_populate_caps_tree(caps: Capabilities)` → build param tree from capabilities (see above);
  connect each action parameter's `sigActivated` → `_open_director_for(cap_name, cap_type)`
- `_open_director_for(cap_name: str, cap_type: str)` →
  - `cap_type == 'variable'` → `create_load_daq_move('Simple')`, pre-fill settings, `show()`
  - `cap_type == 'observable'` → `create_load_daq_viewer(grabber_type=...)`, pre-fill, `show()`
  - Store `(shared_ui, module)` in `_open_directors[cap_name]` to manage lifecycle
- `_open_all_directors(caps)` → call `_open_director_for` for every variable and observable
- `closeEvent()` → `stop_actor()` → `close_instrument()` → close all open director windows
  → `thread.quit()`

**`main()`**: `mkQApp` + `DockArea` + `PymodaqActorGUI(dockarea)` + `app.exec()`

---

### New: `packages/pymodaq/tests/utils/leco/test_actor_gui.py`
Headless tests (mock plugin, mock `PymodaqActor`, Qt-guarded via `pytest.importorskip`):
- `test_plugin_lists_populated` — `ACTUATOR_NAMES` / `DET_TYPES` non-empty
- `test_worker_init_ok` — mock `ini_stage` → `INSTRUMENT_INIT(True)` emitted
- `test_worker_init_fail` — `ini_stage` raises → `ERROR` emitted
- `test_worker_start_stop` — mock `actor.listen` → `ACTOR_READY` then `ACTOR_STOPPED`
- `test_caps_tree_populated` — `_populate_caps_tree` with mock Capabilities → correct param nodes
- `test_caps_tree_action_opens_director` — action button click → `create_load_daq_move` called
- `test_auto_open_all` — `auto_open_all=True` → all directors opened on `ACTOR_READY`
- `test_close_stops_thread` — `closeEvent` → `stop_actor` called, director windows closed

---

### Modified: `packages/pymodaq/src/pymodaq/utils/leco/actor.py`
Add:
```python
def notify_directors(self, event_type: str, message: str) -> None:
    """RPC push event notification to all registered directors."""
    for name in list(self._director_registry):
        try:
            self.communicator.ask_rpc(
                receiver=name,
                method=PymodaqActorMethods.NOTIFY_EVENT,
                event_type=event_type,
                message=message,
            )
        except JSONRPCError as exc:
            if exc.rpc_error.code in (RECEIVER_UNKNOWN.code, NODE_UNKNOWN.code):
                self._director_registry.discard(name)
```
Call sites: on instrument init, on actor start, on error, on state change.

---

### Modified: `packages/pymodaq/src/pymodaq/utils/leco/rpc_method_definitions.py`
```python
class PymodaqActorMethods(StrEnum):
    ...
    NOTIFY_EVENT = "notify_event"

class GenericDirectorMethods(StrEnum):
    ...
    NOTIFY_EVENT = "notify_event"
```

---

### Modified: `packages/pymodaq/src/pymodaq/utils/leco/leco_director.py`
Register in `LECODirector.__init__`:
```python
self.register_rpc_methods((self.notify_event,))
```
```python
def notify_event(self, event_type: str, message: str, additional_payload=None) -> None:
    self.emit_status(ThreadCommand(
        "actor_event",
        attribute={"type": event_type, "message": message},
    ))
```

---

### Modified: `packages/pymodaq/pyproject.toml`
```toml
[project.scripts]
pymodaq-actor-gui = "pymodaq.utils.leco.actor_gui:main"
```

---

## Plugin Discovery
```python
from pymodaq.control_modules.instruments import ACTUATOR_NAMES, DET_TYPES
# ACTUATOR_NAMES: list[str]
# DET_TYPES: list[dict]  — 'name', 'dimension' keys
```
Plugin class loading (same as `actor_main` in `actor.py`):
```python
module = importlib.import_module(f"pymodaq_plugins_xxx.daq_move_{name}")
cls = getattr(module, f"DAQ_Move_{name}")
```

---

## Director Window Pre-configuration
```python
from pymodaq.utils.gui_utils.loader_utils import create_load_daq_move, create_load_daq_viewer

# Variable → DAQ_Move:
shared_ui, daq_move = create_load_daq_move('Simple')
daq_move.settings['actor_name'] = self.settings['actor_name']
daq_move.settings['host'] = 'localhost'
daq_move.settings['use_legacy_actor'] = False
shared_ui.show()

# Observable → DAQ_Viewer (dimension from Capabilities.observables[name].shape):
shared_ui, daq_viewer = create_load_daq_viewer(grabber_type='0D')  # or 1D/2D
daq_viewer.settings['actor_name'] = self.settings['actor_name']
daq_viewer.settings['host'] = 'localhost'
daq_viewer.settings['use_legacy_actor'] = False
shared_ui.show()
```
Director windows are independent — closing them does not stop the actor.

---

## Verification

```bash
# 1. Headless unit tests
PYTHONPATH=/d/Work/PyMoDAQ/packages/pymodaq_utils/src:/d/Work/PyMoDAQ/packages/pymodaq_data/src:\
/d/Work/PyMoDAQ/packages/pymodaq_gui/src:/d/Work/PyMoDAQ/packages/pymodaq/src \
  python3 -m pytest packages/pymodaq/tests/utils/leco/test_actor_gui.py -v

# 2. GUI smoke test
python3 -m pymodaq.utils.leco.actor_gui
# → Select Actuator → MockStage → Init → Start Actor
# → Capabilities dock populates with "position" variable
# → Click [Start DAQ_Move ▶] → director window opens

# 3. Full integration (coordinator + proxy running)
# → Start actor GUI: MockStage, Init, Start Actor
# → Director window opens; position updates; test move_abs

# 4. Multi-capability (camera) integration
# → Actor exposes 'exposure_time' variable + 'frame' observable
# → Both [Start DAQ_Move ▶] and [Start DAQ_Viewer ▶] appear in tree
# → Both director windows open and work independently
```
