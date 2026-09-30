# Engine comparison: `workflow_manager.Workflow` vs `python-statemachine`

`feature/daq_scan_workflow` (custom `Workflow`) vs `experiment/daq_scan_statemachine_v2`
(`python-statemachine`, v2). Both are real, tested ports of `daq_scan.py`. Not a
recommendation — `seb5g`'s call.

The Qt binding layer (`bind_transition`, `bind_toggle`, `bind_enabled_*`, `bind_sync`)
is unchanged, byte-identical on both branches — both engines duck-type the same
interface. Not part of the decision.

## Defining the graph

```python
# Workflow -- runtime, data-driven
workflow = Workflow(name)
workflow.add_state(IDLE, default=True)
workflow.add_transition(START, [IDLE], RUNNING)
workflow.add_transition(PAUSE, [RUNNING], PAUSED)
```
```python
# python-statemachine -- declarative class body
class StandardChart(StateMachine):
    idle = State(initial=True, value=StandardStates.IDLE)
    running = State(value=StandardStates.RUNNING)
    paused = State(value=StandardStates.PAUSED)
    start = idle.to(running)
    pause = running.to(paused)
```

## The one real guard: "no start before an experiment entry is applied"

```python
# Workflow -- a guard, checked on demand
workflow.add_transition(START, [IDLE], RUNNING,
    guard=lambda: bool(self.experiment_manager and self.experiment_manager.entry_applied))
```
```python
# python-statemachine -- modeled as a state instead
class DaqScanChart(StateMachine):
    uninitialized = State(initial=True, value='UNINITIALIZED')
    idle = State(value=StandardStates.IDLE)
    entry_applied = uninitialized.to(idle)
    start = idle.to(running)   # unguarded -- correct by construction
```
Verified directly against the library: `allowed_events` is purely topological,
ignores `cond=` — no side-effect-free "would this succeed" check exists, so a real
`guard=` isn't available here at all. The state-based version is arguably *more*
correct (`entry_applied` is monotonic — can't drift out of sync, no separate check to
maintain), but it costs a transition that must be *fired*, not just *asked* — see
`ChartAdapter.attach_model()` below for the fix to the ordering that cost.



```python
# v2
self.workflow = ChartAdapter(DaqScanChart)   # built before super().__init__(), no model needed
super().__init__(...)
self.workflow.attach_model(self)             # self is a real QObject now
```

## Pause/resume hooks

```python
# Workflow -- explicit registration
self.workflow.on(PAUSE, self._on_pause_triggered)
```
```python
# python-statemachine -- naming convention, zero registration
def after_pause(self, event, source, target):
    ...
```


## Thread safety (found while spiking `invoke`, not adopted — see below)

- `state_changed`-driven UI sync (`bind_transition`/`bind_toggle`/...) is safe from any
  thread: `ChartAdapter` is a `QObject` that never leaves the GUI thread, so Qt
  auto-queues delivery regardless of which thread emits.
- `after_<event>` dispatch is a **plain Python call**, no Qt marshalling — verified it
  runs on whatever thread happens to hold python-statemachine's single shared
  processing lock at that moment. Fixed: `after_pause`/`after_resume` now emit
  `status_message_signal` instead of touching `status_manager` directly (same
  QObject-owns-the-signal trick, verified empirically).

## Pros / cons

| | `workflow_manager.Workflow` | `python-statemachine` (v2) |
|---|---|---|
| Dependency | None | External (`python-statemachine`, optional extra) |
| Guards | `guard=`, checked on demand | None (EAFP only) — model as a state instead |
| Compound/parallel states | Not supported | Built in, tested — the sequencer's actual need |
| Transition hooks | Explicit `.on(name, cb)` | `after_<event>` convention, zero registration |
| Debug/inspector | `WorkflowInspector`, tables only | `MermaidGraphMachine`, live diagram, auto-derived |
| Async worker lifecycle | Manual (`command_daq_signal`/`status_sig` wiring) | `invoke=` could own it — spiked, not adopted (see below) |
| Debuggability | ~150 lines, all yours | Library internals (dispatcher, callback priorities) — needed reading source, not just docs, more than once |

## `invoke` — spiked, deliberately not adopted yet

SCXML-style: a state's `invoke=` spawns work (thread/async) on entry, the handler
calls `ctx.send(event)` on completion — could let `RUNNING` own spawning
`DAQScanAcquisition` and reporting `finished` itself, instead of `start_scan()`/
`stop_scan()`/`thread_status()` manually staying in sync across three methods.

Verified working: background-thread dispatch, `ctx.cancelled` cooperative
cancellation, cross-thread `ctx.send()` transitions. Not adopted because the real
worker (`DAQScanAcquisition`) isn't cooperative with `ctx.cancelled` yet, and an
uncooperative worker's stale event raises `TransitionNotAllowed` — which I confirmed
can surface on a completely unrelated thread's call, not the worker's own, because of
the shared processing lock. Real scope, belongs with the `daq_move`/`daq_viewer` port,
not bolted onto `daq_scan` now. Worth keeping in mind for the STOPPING-state double-start
race noted in `CLAUDE.md`.

## Open items

- Only `daq_scan` ported either way — `daq_move`/`daq_viewer` untouched.
- The sequencer's composite-state design (the actual case for compound/parallel
  states) hasn't been started.
- `WorkFlowActions.LOG` isn't modeled in either branch (pre-existing gap).

## Recommendation

Still not mine to make. `Workflow` for flat lifecycles (`daq_scan`, `daq_logger`,
`daq_move`, `daq_viewer`) — simpler, no dependency, already proven. `python-statemachine`
specifically where compound/parallel states are the actual requirement — today, only
the sequencer.
