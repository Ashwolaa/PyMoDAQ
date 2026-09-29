# Engine comparison: `workflow_manager.Workflow` vs `python-statemachine`

Prompted by [PR #1219's comment](https://github.com/PyMoDAQ/PyMoDAQ/pull/1219#issuecomment-5893125212)
suggesting `python-statemachine` as a replacement for `workflow_manager.py`'s
custom `Workflow` engine. Both are now real, working, tested ports of the
same extension (`daq_scan.py`), not a PoC vs. a hypothetical — the fairest
basis for comparison available.

- **`feature/daq_scan_workflow`** — the existing `Workflow`-based
  implementation.
- **`experiment/daq_scan_statemachine`** — the `python-statemachine`-based
  alternative, built off the same branch.

This doc lays out both side by side. It doesn't pick a winner — that's
`seb5g`'s call as maintainer.

## What's identical either way

The Qt binding layer — `bind_transition()`, `bind_toggle()`,
`bind_enabled_to_states()`, `bind_enabled_to_transition()`, `bind_sync()`,
`Binding`, `action_name_for()` — is unchanged, unmodified, byte-for-byte the
same code on both branches. Both engines duck-type the same interface
(`.trigger()`/`.can_trigger()`/`.trigger_any()`/`.can_trigger_any()`/`.state`/
`.name`/`.state_changed`/`.revalidated`), so this ~140-line layer — arguably
the more valuable half of `workflow_manager.py` — isn't part of the decision
at all.

## Side by side: defining the graph

**`Workflow`** (`standard_workflow.py`):
```python
def standard_workflow(name: str = DEFAULT_WORKFLOW_NAME) -> Workflow:
    IDLE, RUNNING, PAUSED, STOPPING = StandardStates.IDLE, StandardStates.RUNNING, \
        StandardStates.PAUSED, StandardStates.STOPPING

    workflow = Workflow(name)
    workflow.add_state(IDLE, default=True)
    workflow.add_transition(StandardTransitions.START, [IDLE], RUNNING)
    workflow.add_transition(StandardTransitions.PAUSE, [RUNNING], PAUSED)
    workflow.add_transition(StandardTransitions.RESUME, [PAUSED], RUNNING)
    workflow.add_transition(StandardTransitions.STOP, [RUNNING, PAUSED], STOPPING)
    workflow.add_transition(StandardTransitions.FINISHED, [STOPPING, RUNNING], IDLE)
    return workflow
```
Runtime, data-driven — states/transitions are built by calling methods, on
any instance, at any time.

**`python-statemachine`** (`statemachine_workflow.py`'s `StandardChart`):
```python
class StandardChart(StateMachine):
    idle = State(initial=True, value=StandardStates.IDLE)
    running = State(value=StandardStates.RUNNING)
    paused = State(value=StandardStates.PAUSED)
    stopping = State(value=StandardStates.STOPPING)

    start = idle.to(running)
    pause = running.to(paused)
    resume = paused.to(running)
    stop = running.to(stopping) | paused.to(stopping)
    finished = stopping.to(idle) | running.to(idle)
```
Declarative, class-body syntax — arguably more readable as a graph, but
fixed at class-definition time.

## Side by side: `daq_scan`'s real guard

`daq_scan` needs "no start before an experiment entry is applied." This
turned out to be the most instructive difference in the whole comparison.

**`Workflow`** — a guard, checked on demand:
```python
self.workflow = standard_workflow()
# 'start' needs set_scan()'s validation first (see start_scan()), but still gets a
# guard: no start before an experiment entry is applied.
self.workflow.add_transition(
    StandardTransitions.START, [StandardStates.IDLE], StandardStates.RUNNING,
    guard=lambda: bool(self.experiment_manager and self.experiment_manager.entry_applied))
```
`can_trigger('start')` re-evaluates this guard every time it's asked — cheap,
correct, and this is exactly what `bind_transition`'s UI-enabled-sync needs
(a side-effect-free "would this succeed right now" query).

**`python-statemachine`** — this is the one place the port isn't 1:1.
Investigated two of the library's own mechanisms first:

- `cond=`/`validators=` on a transition: neither works for this. Verified
  directly against the installed package source (not just docs) —
  `allowed_events` ignores `cond=` entirely (topology-only), and a guard is
  only actually evaluated by attempting the real transition, which has real
  side effects the instant it succeeds. Unusable for a UI query that must
  never have side effects.

That ruled out python-statemachine's native guard mechanism for this case —
but a deeper look at the actual guard revealed a better fit than either
mechanism:

```python
class DaqScanChart(StateMachine):
    uninitialized = State(initial=True, value='UNINITIALIZED')
    idle = State(value=StandardStates.IDLE)
    running = State(value=StandardStates.RUNNING)
    paused = State(value=StandardStates.PAUSED)
    stopping = State(value=StandardStates.STOPPING)

    entry_applied = uninitialized.to(idle)
    start = idle.to(running)          # unguarded -- correct by construction
    ...
```
`experiment_manager.entry_applied` is monotonic — grepped the whole
codebase; it's set to `True` in exactly two places, never back to `False`
anywhere. That means "an entry has been applied" is a fact about which
*state* the workflow is in, not a condition to keep re-checking — encoding
it as an explicit `UNINITIALIZED` state ahead of `IDLE` makes `start`
correct by construction, no guard needed at all. This is arguably **more
correct** than the `Workflow` version: it can't drift out of sync with
reality, because there's no separate check to forget to update.

The real cost: a state transition has to be *fired*, unlike a guard, which
can be *asked* at any time. `entry_applied` can already be `True` before the
chart exists (a synchronous call during `__init__`), which needed an
explicit catch-up trigger right after construction — a subtlety the
guard-based version never had to think about.

## Side by side: pause/resume hooks

**`Workflow`** — explicit registration:
```python
self.workflow.on(StandardTransitions.PAUSE, self._on_pause_triggered)
self.workflow.on(StandardTransitions.RESUME, self._on_resume_triggered)
```

**`python-statemachine`** — naming convention, zero registration:
```python
def after_pause(self, event, source, target):
    self.command_daq_signal.emit(utils.ThreadCommand('pause_acquisition', attribute=True))
    self.status_manager.set_permanent_status('Acquisition paused')

def after_resume(self, event, source, target):
    ...
```
`after_<event>` methods on the model object are found and called
automatically by the chart's dispatcher — confirmed correctly scoped (START
also lands on `running`, but doesn't spuriously fire `after_resume`).
Slightly less code, no explicit wiring step to forget.

## Pros / cons

| | `workflow_manager.Workflow` | `python-statemachine` |
|---|---|---|
| Dependency | None | New external dependency (already hit one deprecation mid-project: `current_state` → `configuration`) |
| Graph mutable after definition | Partially — `add_transition()` can add a new one, or replace an existing one by re-adding the same name, on a live instance (used by `workflow_inspector_example.py` to bolt on an ad hoc `'fail'` transition, 2 lines, no subclass). No explicit *removal* either. | No, not at all — confirmed both directions empirically: subclassing to override a transition adds a second, unguarded path instead of replacing it, and deleting an inherited transition attribute (`del Subclass.pause`) is purely cosmetic, the transition still fires. The graph is fixed the moment the class body runs. |
| Compound / parallel states | Not supported | Built in and tested (`State.Compound`, `State.Parallel`) — real, verified fit for something like an independent LOG region, and the actual open need for the sequencer's composite-state design |
| Transition-scoped hooks | Explicit `.on(name, callback)` registration | `after_<event>` naming convention, zero registration |
| Debuggability | ~150 lines, all yours, easy to step through | Async-capable engine, dispatcher, callback-priority system underneath — several behaviors in this comparison needed reading the library's source directly, not just its docs, to get right |

Deliberately left off this table: a "guard support" row and a "maturity"
row. Neither held up as a real differentiator once examined —

- **Guards**: `python-statemachine` has no dry-run API for `cond=`/
  `validators=` (can't check "would this succeed" without attempting it,
  side effects and all). That looked like a clear point for `Workflow`'s
  `guard=` — until the actual case (`daq_scan`'s START guard) turned out to
  be *better* modeled as an explicit `UNINITIALIZED` state than as a guard
  in either engine. So this isn't "engine A can, engine B can't" — it's "the
  right answer usually isn't a guard at all," which applies to both.
- **Maturity**: "only `daq_scan` is ported" is true, but it's a statement
  about how much of this comparison has been done, not a technical property
  of either engine — worth knowing, listed under Open Items, not a pro/con.

## Open items, either way

- **`WorkFlowActions.LOG`** (the "Do Logging" toolbar toggle) isn't modeled
  in either branch's workflow — a pre-existing gap from the original
  `Workflow` draft, not introduced by this comparison. `python-statemachine`
  parallel states are a plausible fit *if* LOG's state should ever actually
  interact with the lifecycle; verified the mechanics work, but it's not
  built, and isn't worth building for a feature whose need is itself
  unconfirmed.
- **No `WorkflowInspector` equivalent** exists for the `python-statemachine`
  side — its transitions live as class descriptors, not a flat runtime
  table, so the existing inspector can't be reused as-is. Not pursued, since
  it's not required for the standard use case.
- **The sequencer's composite-state design** — the one concrete case where
  `python-statemachine`'s real advantage (compound/parallel states) would
  actually be exercised — hasn't been touched by this comparison at all.
- **Only `daq_scan` has been ported.** `daq_move`/`daq_viewer` were next in
  line for `Workflow` before this comparison started; neither has been
  touched against `python-statemachine`. Worth doing before treating this
  comparison as final.

## Recommendation

Not mine to make final, but for what it's worth: keep `Workflow` as the
default for flat lifecycles (`daq_scan`, `daq_logger`, `daq_move`,
`daq_viewer`) — it's simpler, dependency-free, and already proven — and
treat `python-statemachine` as the tool to reach for specifically where
compound/parallel states are the actual requirement, which today means only
the sequencer. Both branches are real and buildable, so `seb5g` can check
out either (or both) and decide directly rather than from a write-up alone.
