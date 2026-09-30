"""
DRAFT — experimental, not wired into CustomApp. python-statemachine analog of
standard_workflow.py, for comparing it against workflow_manager.Workflow as the
engine behind the IDLE/RUNNING/PAUSED/STOPPING lifecycle. See STATEMACHINE_REVIEW.md.

* ``StandardChart``: same graph as standard_workflow().
* ``ChartAdapter``: duck-types Workflow's query/trigger surface (.trigger()/
  .can_trigger()/.trigger_any()/.can_trigger_any()/.state/.name/.state_changed/
  .revalidated) so the existing bind_* functions work unmodified. Not
  constructor-compatible: no ``model=`` kwarg -- see ``attach_model()``.
* ``standard_chart()``: the ChartAdapter-returning analog of standard_workflow().

No guard support (no `cond=`/`validators=`): `allowed_events` is purely
topological, ignores `cond=` -- there's no side-effect-free "would this
succeed" check to build can_trigger() on. Model a guard as a state instead
(see daq_scan.py's DaqScanChart) -- this is the library's own idiom (EAFP:
attempt + catch TransitionNotAllowed), not a gap to paper over.

Requires: pip install python-statemachine (packages/pymodaq_gui[statemachine]).
Diagram export (statemachine_inspector.py): [statemachine-diagrams] extra.
"""
from statemachine import StateMachine, State
from statemachine.exceptions import TransitionNotAllowed
from qtpy import QtCore

from pymodaq_gui.managers.workflow_manager import DEFAULT_WORKFLOW_NAME
from pymodaq_gui.managers.standard_workflow import StandardStates


class StandardChart(StateMachine):
    """ Same graph as standard_workflow(). Validation with side effects (e.g.
    daq_scan's set_scan()) belongs in bind_transition()'s click_slot, run once
    at click time -- never in `cond=`, re-evaluated on every UI resync. """
    idle = State(initial=True, value=StandardStates.IDLE)
    running = State(value=StandardStates.RUNNING)
    paused = State(value=StandardStates.PAUSED)
    stopping = State(value=StandardStates.STOPPING)

    start = idle.to(running)
    pause = running.to(paused)
    resume = paused.to(running)
    stop = running.to(stopping) | paused.to(stopping)
    finished = stopping.to(idle) | running.to(idle)


class ChartAdapter(QtCore.QObject):
    """ Makes a python-statemachine chart duck-type Workflow's query/trigger
    surface. See module docstring for why there's no `cond=`/guard support,
    and why `model` is attached separately from construction. """
    state_changed = QtCore.Signal(object, object)
    revalidated = QtCore.Signal()

    def __init__(self, chart_cls: type[StateMachine], name: str = DEFAULT_WORKFLOW_NAME):
        super().__init__()
        self.name = name
        self.chart = chart_cls()
        self.chart.add_listener(self)

    def attach_model(self, model):
        """ Register `model` as a chart listener: its after_<event>/before_<event>
        methods (if any) then get dispatched automatically. Unlike `model=` at
        construction, `model` can be attached whenever it's ready (e.g. once past
        QObject.__init__()) -- call once, any transitions before that are fine,
        this only affects dispatch from here on. """
        self.chart.add_listener(model)

    def after_transition(self, event, source, target):
        """ Listener method (see __init__): python-statemachine calls this on
        every listener after any transition, regardless of event name. """
        self.state_changed.emit(str(source.value), str(target.value))

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
        """ Same as Workflow.revalidate(): resync bindings with no actual
        transition -- for a bind_enabled() predicate whose input changed on
        its own. """
        self.revalidated.emit()


def standard_chart(name: str = DEFAULT_WORKFLOW_NAME) -> ChartAdapter:
    """ ChartAdapter-returning analog of standard_workflow(name). Call
    `.attach_model(extension_instance)` once it's constructed. """
    return ChartAdapter(StandardChart, name)
