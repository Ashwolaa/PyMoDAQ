# Plan: PymodaqActor GUI (`actor_gui.py`)

---

## Open Issues & Design Decisions

The following issues were identified during plan review. Sections marked **RESOLVED** have been
updated in the plan body; sections marked **DEFERRED** are tracked but not yet implemented.

### Issue 1 — `create_load_daq_viewer` has no `grabber_type` parameter — RESOLVED
The actual signature (`loader_utils.py:42`) is `create_load_daq_viewer() -> tuple[SharedUI, DAQ_Viewer]`
with no arguments.  Grabber type is set **after** creation via
`daq_viewer.detector = SelectedModule(DAQTypesEnum[det_type], detector)`.
The Director Window Pre-configuration section has been updated accordingly.

### Issue 2 — `instruments.py` raises on import when no plugins installed — RESOLVED
`from pymodaq.control_modules.instruments import ACTUATOR_NAMES, DET_TYPES` raises
`DetectorError`/`ActuatorError` at module import time if no plugins exist.
The GUI must wrap this import in a try/except and show an informative message
rather than crashing at startup.  Handled in `_on_plugin_type_changed()` and the `main()` bootstrap.

### Issue 3 — `PymodaqActor` takes `device_class`, not an instance — RESOLVED
Plugin instantiation with `parent=None` already works: `DAQ_Move_base.__init__` creates
`self.settings` from `self.params` with no hardware touched; `parent=None` only sets a title
fallback and silences `emit_status()` — the same behaviour as in `DAQ_Move`/`DAQ_Viewer` before
the user clicks "Init".  The workflow mirrors the existing pattern exactly:

1. Plugin selected → `plugin_class()` → `plugin.settings` shown in Settings dock
2. **"Init Instrument"** → `plugin.ini_stage()` / `plugin.ini_detector()` → hardware connected
3. **"Start Actor"** → `_InstanceFactory(plugin)` passed as `device_class` to `PymodaqActor`

The only non-trivial part is step 3: `PymodaqActor` expects a callable class, not an instance.
`_InstanceFactory` solves this cleanly (see **Plugin Initialization Design** section).

### Issue 4 — `notify_directors` / `NOTIFY_EVENT` scope — DEFERRED
`notify_directors()`, `NOTIFY_EVENT` enum entries, and `LECODirector.notify_event()` are useful
for pushing actor state changes to remote director GUIs, but they are not needed for `actor_gui.py`
itself (the GUI knows actor state directly via `ActorWorker` signals).
Deferred to a separate PR to keep `actor_gui.py` reviewable on its own.

### Issue 5 — Settings pre-filling uses wrong access pattern — RESOLVED
`Parameter` is not a dict.  `settings['actor_name']` does not work.
The correct pattern is `settings.child('actor_name').setValue(...)`.
Also, `actor_name` / `host` / `use_legacy_actor` live inside the **plugin's** settings tree
(added by `LECODirector` mixin), not directly on `DAQ_Move`.
Director pre-configuration must use `daq_move.settings.child('main_settings', 'actor_name').setValue(...)`
or the equivalent path.  The Director Window Pre-configuration section has been updated.

### Issue 6 — LED widget class not specified — RESOLVED
Use `pymodaq_gui.utils.widgets.led.QLED` (consistent with the rest of the codebase).

### Issue 7 — `ActorState` usage unclear — RESOLVED
`ActorState` is an **internal worker** concept only.  The GUI tracks state exclusively via
`ThreadCommand` values received through `status_sig`.  No parallel state variable in the GUI class.

### Issue 8 — `plugin_type` naming inconsistency — RESOLVED
`plugin_type` limits now use `['Actuator', 'DAQ0D', 'DAQ1D', 'DAQ2D']` to match the
`DET_TYPES` keys from `instruments.py`.

### Issue 9 — `closeEvent` thread cleanup — RESOLVED
`closeEvent` calls `thread.quit(); thread.wait()` after stopping the actor and closing
director windows, to prevent Qt crash-on-destruction.

---

## Plugin Initialization Design (Issue #3)

The flow mirrors what `DAQ_Move` / `DAQ_Viewer` already do.  `DAQ_Move_base.__init__` with
`parent=None` creates `self.settings` from `self.params` with no hardware involvement.
The plugin is ready to show its settings tree immediately.  `ini_stage()` / `ini_detector()`
is only called when the user explicitly clicks **"Init Instrument"**.

The only non-trivial part: `PymodaqActor` expects a callable `device_class`, not an instance.
`_InstanceFactory` satisfies that protocol using the already-initialized plugin.

```python
class _InstanceFactory:
    """Wraps an initialized plugin so pyleco.Actor can call device_class() as expected."""
    def __init__(self, instance):
        self._instance = instance
    def __call__(self):
        return self._instance
```

**`ActorWorker` slot sequence:**

```python
def init_instrument(self, plugin_class, params_state=None):
    """Phase 1 — instantiate plugin and open hardware (mirrors DAQ_Move 'Init' button)."""
    plugin = plugin_class(parent=None, params_state=params_state)
    # plugin.settings is now available; show it in the Settings dock via INSTRUMENT_INIT signal
    try:
        init_method = plugin.ini_stage if hasattr(plugin, 'ini_stage') else plugin.ini_detector
        status = init_method()
    except Exception as exc:
        self.status_sig.emit(ThreadCommand('ERROR', str(exc)))
        return
    if not status.get('initialized', False):
        self.status_sig.emit(ThreadCommand('ERROR', status.get('info', 'Init failed')))
        return
    self._plugin = plugin
    self.status_sig.emit(ThreadCommand('INSTRUMENT_INIT', plugin))  # GUI displays plugin.settings

def start_actor(self, name, host, port):
    """Phase 2 — wrap initialized plugin and start the LECO actor."""
    self._actor = PymodaqActor(name=name, device_class=_InstanceFactory(self._plugin),
                               host=host, port=port)
    self._stop_event = threading.Event()
    threading.Thread(target=self._actor.listen, args=(self._stop_event,),
                     daemon=True, name=f"actor-{name}").start()
    caps = Capabilities.from_dict(self._actor.get_capabilities())
    self.status_sig.emit(ThreadCommand('ACTOR_READY', caps))
```

`ini_stage()` vs `ini_detector()` is determined by plugin type:
`Actuator` → `ini_stage()`; `DAQ0D`/`DAQ1D`/`DAQ2D` → `ini_detector()`.
Plugins must also implement `read()` / `write()` for `PymodaqActor` to call them.

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

After the actor starts and signs into the coordinator, the GUI fetches `get_capabilities()` and
displays a tree of what the actor offers:

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

An **"Auto-open all directors"** checkbox in settings opens all directors automatically when the
actor reaches READY state.

---

## Implementation of the Capabilities Tree

Use PyMoDAQ's `Parameter` / `ParameterTree` system for consistency with the rest of the codebase.
Built dynamically from `Capabilities` after `ACTOR_READY`:

```python
caps_params = [
    {'name': 'Variables', 'type': 'group', 'children': [
        {'name': 'position', 'type': 'group', 'children': [
            {'name': 'type',    'type': 'str',   'value': 'continuous', 'readonly': True},
            {'name': 'min',     'type': 'float', 'value': -100.0,       'readonly': True},
            {'name': 'max',     'type': 'float', 'value':  100.0,       'readonly': True},
            {'name': 'epsilon', 'type': 'float', 'value': 0.001,        'readonly': True},
            {'name': 'Open DAQ_Move', 'type': 'action'},
        ]},
    ]},
    {'name': 'Observables', 'type': 'group', 'children': [
        {'name': 'frame', 'type': 'group', 'children': [
            {'name': 'shape', 'type': 'str', 'value': '(1024, 1024)', 'readonly': True},
            {'name': 'Open DAQ_Viewer', 'type': 'action'},
        ]},
    ]},
]
```

`'action'` type parameters render as buttons. `sigActivated` on each →
`_open_director_for(cap_name, cap_type)`.

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
├── Capabilities dock  (hidden until ACTOR_READY)
│   └── ParameterTree built from Capabilities
│       Variables group   → each: properties + [Start DAQ_Move ▶] action
│       Observables group → each: properties + [Start DAQ_Viewer ▶] action
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
    ├── Plugin instance  (DAQ_Move_base or DAQ_Viewer_base subclass)
    ├── PymodaqActor     (wraps plugin; actor.listen runs in its own sub-thread)
    └── status_sig = Signal(ThreadCommand)
```

Worker → GUI ThreadCommands:
| Command         | Attribute    | Meaning                              |
|---|---|---|
| INSTRUMENT_INIT | bool         | Instrument init success/failure      |
| ACTOR_READY     | Capabilities | Actor up; capabilities to display    |
| ACTOR_STOPPED   | —            | Actor shut down cleanly              |
| UPDATE_STATUS   | str          | Status bar text                      |
| ERROR           | str          | Error message                        |

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
    {'name': 'actor_name',    'type': 'str',  'value': 'actor'},
    {'name': 'host',          'type': 'str',  'value': 'localhost'},
    {'name': 'port',          'type': 'int',  'value': COORDINATOR_PORT},
    {'name': 'plugin_type',   'type': 'list', 'limits': ['Actuator', 'DAQ0D', 'DAQ1D', 'DAQ2D']},  # matches DET_TYPES keys
    {'name': 'plugin_name',   'type': 'list', 'limits': []},
    {'name': 'auto_open_all', 'type': 'bool', 'value': False,
     'tip': 'Open a director window for every capability when actor starts'},
]
```

Key methods:
- `setup_docks()` → LECO dock + Capabilities dock (initially hidden) + Settings dock
- `setup_actions()` → Init / Start / Stop toolbar buttons
- `connect_things()` → buttons → worker slots; `status_sig` → `_on_status`
- `_on_plugin_type_changed()` → repopulate plugin_name list from `ACTUATOR_NAMES` / `DET_TYPES`
- `_on_plugin_selected()` → load plugin class; show its `settings_tree` in Settings dock
- `_on_status(cmd: ThreadCommand)` → update LEDs / buttons / status bar;
  on `ACTOR_READY`: call `_populate_caps_tree(caps)`, show Capabilities dock,
  if `auto_open_all` → `_open_all_directors(caps)`
- `_populate_caps_tree(caps: Capabilities)` → build param tree (see above);
  connect each action parameter's `sigActivated` → `_open_director_for(cap_name, cap_type)`
- `_open_director_for(cap_name: str, cap_type: str)` →
  - `'variable'` → `create_load_daq_move('Simple')`, pre-fill, `show()`
  - `'observable'` → `create_load_daq_viewer(grabber_type=...)`, pre-fill, `show()`
  - Store in `_open_directors[cap_name]` to manage lifecycle
- `_open_all_directors(caps)` → call `_open_director_for` for every variable and observable
- `closeEvent()` → `stop_actor()` → `close_instrument()` → close all open director windows
  → `thread.quit(); thread.wait()`  *(Issue 9: wait() prevents Qt crash on destruction order)*

**`main()`**: `mkQApp` + `DockArea` + `PymodaqActorGUI(dockarea)` + `app.exec()`

---

### New: `packages/pymodaq/tests/utils/leco/test_actor_gui.py`
Headless tests (mock plugin, mock `PymodaqActor`, Qt-guarded via `pytest.importorskip`):
- `test_plugin_lists_populated` — `ACTUATOR_NAMES` / `DET_TYPES` non-empty
- `test_worker_init_ok` — mock `ini_stage` → `INSTRUMENT_INIT(True)` emitted
- `test_worker_init_fail` — `ini_stage` raises → `ERROR` emitted
- `test_worker_start_stop` — mock `actor.listen` → `ACTOR_READY` then `ACTOR_STOPPED`
- `test_caps_tree_populated` — `_populate_caps_tree` with mock Capabilities → correct param nodes created
- `test_caps_tree_action_opens_director` — action button click → `create_load_daq_move` called
- `test_auto_open_all` — `auto_open_all=True` → all directors opened on `ACTOR_READY`
- `test_close_stops_thread` — `closeEvent` → `stop_actor` called, director windows closed

---

### Modified: `packages/pymodaq/src/pymodaq/utils/leco/actor.py` — DEFERRED (Issue 4)
`notify_directors()` and `NOTIFY_EVENT` are useful for pushing actor state changes to remote
director GUIs but are not needed for `actor_gui.py` itself.  Deferred to a follow-up PR.

### Modified: `packages/pymodaq/src/pymodaq/utils/leco/rpc_method_definitions.py` — DEFERRED (Issue 4)

### Modified: `packages/pymodaq/src/pymodaq/utils/leco/leco_director.py` — DEFERRED (Issue 4)

---

### Modified: `packages/pymodaq/pyproject.toml`
```toml
[project.scripts]
pymodaq-actor-gui = "pymodaq.utils.leco.actor_gui:main"
```

---

## Plugin Discovery

> **Note (Issue 2):** `instruments.py` raises `DetectorError`/`ActuatorError` at import time
> if no plugins are installed.  Guard the import.

```python
try:
    from pymodaq.control_modules.instruments import ACTUATOR_NAMES, DET_TYPES
except Exception as exc:
    ACTUATOR_NAMES = []
    DET_TYPES = {'DAQ0D': [], 'DAQ1D': [], 'DAQ2D': []}
    logger.warning("No plugins installed: %s", exc)
```

Plugin class loading (same pattern as `actor_main` in `actor.py`):
```python
module = importlib.import_module(f"pymodaq_plugins_xxx.daq_move_{name}")
cls = getattr(module, f"DAQ_Move_{name}")
```

`plugin_type` dropdown limits: `['Actuator', 'DAQ0D', 'DAQ1D', 'DAQ2D']` matching `DET_TYPES` keys.

---

## Director Window Pre-configuration

Director windows use **`DAQ_Move_LECODirector`** (for variables) and **`DAQ_xDViewer_LECODirector`**
(for observables) — the existing LECO director plugins that already implement `ini_stage()` /
`ini_detector()` to connect to the actor via LECO, and handle all RPC / ZMQ data-channel wiring.
The actor GUI pre-fills `actor_name`, `host`, and `use_legacy_actor=False` so the user can just
click "Init" in the director window.

```python
from pymodaq.utils.gui_utils.loader_utils import create_load_daq_move, create_load_daq_viewer
from pymodaq.control_modules.daq_viewer_ui.viewer_selector import SelectedModule
from pymodaq.control_modules.instruments import DAQTypesEnum

# Variable → DAQ_Move with DAQ_Move_LECODirector plugin pre-selected:
shared_ui, daq_move = create_load_daq_move('Simple')
daq_move.actuator = 'LECODirector'          # selects DAQ_Move_LECODirector plugin
# leco_parameters live at the plugin settings level; path confirmed from DAQ_Move_LECODirector.params
daq_move.settings.child('move_settings', 'actor_name').setValue(self.settings['actor_name'])
daq_move.settings.child('move_settings', 'host').setValue(self.settings['host'])
daq_move.settings.child('move_settings', 'use_legacy_actor').setValue(False)
shared_ui.show()

# Observable → DAQ_Viewer with DAQ_xDViewer_LECODirector plugin pre-selected:
# shape ndim 1 → 'DAQ0D', 2 → 'DAQ1D', 3 → 'DAQ2D'
ndim = len(obs.shape)
det_type = {1: 'DAQ0D', 2: 'DAQ1D', 3: 'DAQ2D'}.get(ndim, 'DAQ0D')
shared_ui, daq_viewer = create_load_daq_viewer()
daq_viewer.detector = SelectedModule(DAQTypesEnum[det_type], 'LECODirector')
daq_viewer.settings.child('detector_settings', 'actor_name').setValue(self.settings['actor_name'])
daq_viewer.settings.child('detector_settings', 'host').setValue(self.settings['host'])
daq_viewer.settings.child('detector_settings', 'use_legacy_actor').setValue(False)
shared_ui.show()
```

> **Note (Issue 1 & 5):** exact `settings.child(...)` paths must be verified at runtime once
> `DAQ_Move_LECODirector` / `DAQ_xDViewer_LECODirector` are instantiated — `leco_parameters`
> are appended to `params` at class level so the tree structure is known, but the root group
> name (`move_settings` vs `detector_settings`) should be confirmed.
> Parameter access uses `.child(...).setValue(...)`, not dict subscript.

Director windows are independent — closing them does not stop the actor.

---

## Implementation Status

| File | Status |
|---|---|
| `packages/pymodaq/src/pymodaq/utils/leco/actor_gui.py` | **Written** — needs smoke-test |
| `packages/pymodaq/tests/utils/leco/test_actor_gui.py`  | **Written** — needs `pytest` run |
| `packages/pymodaq/pyproject.toml` (entry point)        | **TODO** |

### Open questions found during implementation

1. **`move_settings` path for LECODirector params** — `leco_parameters` are appended to
   `DAQ_Move_LECODirector.params` at class level.  The root group name where they land
   (assumed `'move_settings'`) must be verified by inspecting the live parameter tree.
   Same for `'detector_settings'` in the viewer director.  If wrong, the pre-fill will
   silently fail (guarded by try/except with a warning log).

2. **`PymodaqActor.listen()` keyword vs positional** — `actor_main()` calls
   `actor.listen(stop_event=stop_event)` (keyword).  Confirmed in `ActorWorker.start_actor`.

3. **`ParameterTree` root item access in tests** — retrieving the root `Parameter` from a
   `ParameterTree` widget for test assertions is not straightforward; the action-button
   connection test is partially structural.  Consider exposing `_caps_param_root` for
   easier test access.

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
# → Capabilities dock shows: Variables / position / [Start DAQ_Move ▶]
# → Click button → director window opens

# 3. Full integration (coordinator + proxy running)
# → Init + Start Actor; director auto-opens if checkbox set
# → Verify position updates; test move_abs from director

# 4. Multi-capability (camera) integration
# → Actor exposes 'exposure_time' (variable) + 'frame' (observable)
# → Both [Start DAQ_Move ▶] and [Start DAQ_Viewer ▶] in tree
# → Both director windows work independently
```
