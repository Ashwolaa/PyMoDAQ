"""
DRAFT — experimental, not wired into CustomApp. Comparison alternative to
standard_workflow.py, per PR #1219's suggestion to evaluate python-statemachine
(https://python-statemachine.readthedocs.io/) as the engine behind the
IDLE/RUNNING/PAUSED/STOPPING lifecycle.

* ``StandardChart``: the same graph as standard_workflow()'s, built with
  python-statemachine instead of workflow_manager.Workflow.
* ``ChartAdapter``: makes a StandardChart duck-type as a Workflow -- only
  the surface workflow_manager.py's bind_transition()/bind_toggle()/
  bind_enabled_to_states()/bind_enabled_to_transition() actually touch
  (.trigger()/.can_trigger()/.trigger_any()/.can_trigger_any()/.state/
  .name/.state_changed/.revalidated). Confirmed those work completely
  unmodified against it -- see STATEMACHINE_REVIEW.md for the empirical
  trail. bind_standard_workflow_actions()/bind_pause_action() from
  standard_workflow.py also work unmodified for the same reason.
* ``standard_chart()``: the ChartAdapter-returning analog of
  standard_workflow().

--- Three things that don't port 1:1, all handled here ------------------
1. State VALUES: python-statemachine's `.id` is always the lowercase
   attribute name (`value=` doesn't change that) -- but existing code/tests
   compare `workflow.state == 'RUNNING'` (uppercase, via StandardStates).
   States are declared with explicit `value=StandardStates.RUNNING` etc.,
   and ChartAdapter.state reads `.value`, not `.id`.
2. Transition-specific hooks: today's `workflow.on(StandardTransitions.PAUSE,
   callback)` registers a callback scoped to exactly that transition (NOT
   "any entry into PAUSED" -- START also lands on RUNNING but must not
   re-fire a RESUME-scoped hook). The python-statemachine-native equivalent
   is a method named `after_<event>` defined directly on the `model` object
   (confirmed empirically to be called by the dispatcher, correctly scoped,
   with zero extra registration code) -- so a DAQScan-like model would
   define `after_pause`/`after_resume` methods directly instead of calling
   `workflow.on(...)` in connect_things().
3. Guards do NOT go through python-statemachine's `cond=` here -- confirmed
   empirically (against the actual installed package source, not just
   docs) that there is no dry-run/is_valid API: `allowed_events` ignores
   `cond=` entirely (reflects state-topology reachability only), and the
   guard is only actually evaluated by attempting the real transition,
   which has real side effects the instant it succeeds. That's unusable
   for a UI-enabled-sync check, which must never have side effects. So
   ChartAdapter takes its own `guards={event_name: callable}` dict instead
   -- exactly workflow_manager.Workflow's `guard=` parameter, evaluated
   entirely on the Python side, independent of the chart. This also means
   a chart with a guard doesn't need its own subclass (see daq_scan.py's
   real port: it reuses this module's StandardChart as-is, passing
   `guards={'start': self.can_start}` to ChartAdapter instead of defining
   its own chart class) -- python-statemachine handles states/transitions/
   hooks only, guards stay exactly where workflow_manager.Workflow already
   put them.

Requires: pip install python-statemachine (packages/pymodaq_gui[statemachine]).
"""
from collections.abc import Callable

from statemachine import StateMachine, State
from statemachine.exceptions import TransitionNotAllowed
from qtpy import QtCore

from pymodaq_gui.managers.workflow_manager import DEFAULT_WORKFLOW_NAME
from pymodaq_gui.managers.standard_workflow import StandardStates


class StandardChart(StateMachine):
    """ python-statemachine analog of standard_workflow()'s graph -- same
    states, same five transitions, same (lack of a) START guard: set_scan()
    validation stays a one-shot click-time check (bind_transition's
    click_slot), not a `cond=` -- `cond=` is re-evaluated on every UI
    resync (bind_transition's enabled-sync runs on every state_changed),
    and set_scan() has real side effects (h5 node creation, message
    boxes) that must not run just to render a button's enabled state. """
    idle = State(initial=True, value=StandardStates.IDLE)
    running = State(value=StandardStates.RUNNING)
    paused = State(value=StandardStates.PAUSED)
    stopping = State(value=StandardStates.STOPPING)

    start = idle.to(running)
    pause = running.to(paused)
    resume = paused.to(running)
    stop = running.to(stopping) | paused.to(stopping)
    finished = stopping.to(idle) | running.to(idle)

    def after_transition(self, event, source, target):
        self.adapter.state_changed.emit(str(source.value), str(target.value))


class ChartAdapter(QtCore.QObject):
    """ Makes a python-statemachine chart duck-type as a
    workflow_manager.Workflow. See module docstring for what this is and
    isn't for -- in particular, why `guards` exists and `cond=` isn't
    used. """
    state_changed = QtCore.Signal(object, object)
    revalidated = QtCore.Signal()

    def __init__(self, chart_cls: type[StateMachine], model, name: str = DEFAULT_WORKFLOW_NAME,
                guards: dict[str, Callable[[], bool]] | None = None):
        super().__init__()
        self.name = name
        self.chart = chart_cls(model=model)
        self.chart.adapter = self
        self._guards = guards or {}

    @property
    def state(self) -> str:
        return str(next(iter(self.chart.configuration)).value)

    def can_trigger(self, name: str) -> bool:
        if name not in [str(e) for e in self.chart.allowed_events]:
            return False
        guard = self._guards.get(name)
        return guard() if guard is not None else True

    def trigger(self, name: str) -> bool:
        if not self.can_trigger(name):
            return False
        try:
            getattr(self.chart, name)()
            return True
        except TransitionNotAllowed:
            return False

    def can_trigger_any(self, *names: str) -> bool:
        return any(self.can_trigger(n) for n in names)

    def trigger_any(self, *names: str) -> bool:
        for n in names:
            if self.can_trigger(n):
                return self.trigger(n)
        return False

    def revalidate(self):
        """ Same as Workflow.revalidate(): resync every binding without an
        actual transition, e.g. daq_scan's do_things_after_experiment_set()
        re-checking the START guard when entry_applied changes on its own. """
        self.revalidated.emit()


def standard_chart(model, name: str = DEFAULT_WORKFLOW_NAME,
                   guards: dict[str, Callable[[], bool]] | None = None) -> ChartAdapter:
    """ The ChartAdapter-returning analog of standard_workflow(name) --
    `model` is the object whose after_<event>/before_<event> methods (if
    any) the chart's dispatcher will call, e.g. the DAQScan/DAQLogger
    extension instance itself. `guards`, e.g. {'start': self.can_start} --
    see ChartAdapter's docstring for why this replaces `cond=`. """
    return ChartAdapter(StandardChart, model, name, guards=guards)
