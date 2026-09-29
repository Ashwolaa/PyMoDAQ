"""
DRAFT — experimental, not wired into CustomApp. python-statemachine analog of
standard_workflow.py, for comparing it against workflow_manager.Workflow as
the engine behind the IDLE/RUNNING/PAUSED/STOPPING lifecycle (PR #1219).

* ``StandardChart``: the same graph as standard_workflow()'s.
* ``ChartAdapter``: wraps a chart so it duck-types workflow_manager.Workflow
  (.trigger()/.can_trigger()/.trigger_any()/.can_trigger_any()/.state/.name/
  .state_changed/.revalidated) -- bind_transition()/bind_toggle()/
  bind_enabled_to_states()/bind_enabled_to_transition() and
  bind_standard_workflow_actions()/bind_pause_action() all work against it
  unmodified.
* ``standard_chart()``: the ChartAdapter-returning analog of
  standard_workflow().

Two things that don't map 1:1 onto python-statemachine, handled here:

* **State values.** A State's ``.id`` is always its lowercase attribute name
  (``value=`` doesn't change that), but existing code compares
  ``workflow.state == 'RUNNING'``. States are declared with explicit
  ``value=StandardStates.RUNNING`` etc., and ``ChartAdapter.state`` reads
  ``.value``, not ``.id``.
* **Transition-specific hooks.** ``workflow.on(PAUSE, callback)`` scopes a
  callback to exactly one transition (not "any entry into PAUSED" -- START
  also lands on RUNNING). The equivalent here is a method named
  ``after_<event>`` defined directly on the model passed to ChartAdapter --
  called automatically, no registration call needed.

No guard support here (no `cond=`/`validators=`): neither offers a way to
check "would this succeed" without actually attempting the transition, which
rules them out for a side-effect-free UI-enabled check. Model a guard as a
state instead where possible (see daq_scan.py's DaqScanChart for a worked
example). If a truly reversible guard ever comes up, add a small
``guards={event_name: callable}`` dict to ChartAdapter then -- not built
speculatively here.

Requires: pip install python-statemachine (packages/pymodaq_gui[statemachine]).
"""
from statemachine import StateMachine, State
from statemachine.exceptions import TransitionNotAllowed
from qtpy import QtCore

from pymodaq_gui.managers.workflow_manager import DEFAULT_WORKFLOW_NAME
from pymodaq_gui.managers.standard_workflow import StandardStates


class StandardChart(StateMachine):
    """ python-statemachine analog of standard_workflow()'s graph: same
    states, same five transitions. Validation with real side effects (e.g.
    daq_scan's set_scan()) belongs in bind_transition()'s click_slot, run
    once at click time -- never in `cond=`, which gets re-evaluated on every
    UI resync. """
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
    isn't for -- in particular, why there's no `cond=`/guard support here. """
    state_changed = QtCore.Signal(object, object)
    revalidated = QtCore.Signal()

    def __init__(self, chart_cls: type[StateMachine], model, name: str = DEFAULT_WORKFLOW_NAME):
        super().__init__()
        self.name = name
        self.chart = chart_cls(model=model)
        self.chart.adapter = self

    @property
    def state(self) -> str:
        return str(next(iter(self.chart.configuration)).value)

    def can_trigger(self, name: str) -> bool:
        return name in [str(e) for e in self.chart.allowed_events]

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
        actual transition -- for a bind_enabled() predicate whose external
        input changed on its own. """
        self.revalidated.emit()


def standard_chart(model, name: str = DEFAULT_WORKFLOW_NAME) -> ChartAdapter:
    """ The ChartAdapter-returning analog of standard_workflow(name) --
    `model` is the object whose after_<event>/before_<event> methods (if
    any) the chart's dispatcher will call, e.g. the DAQScan/DAQLogger
    extension instance itself. """
    return ChartAdapter(StandardChart, model, name)
