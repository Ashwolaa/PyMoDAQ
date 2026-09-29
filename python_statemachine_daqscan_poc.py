"""
Throwaway PoC -- not part of any package, not wired into anything.

Pushes python_statemachine_adapter.py's result all the way to daq_scan.py's actual shape:
a StandardChart matching standard_workflow()'s IDLE/RUNNING/PAUSED/STOPPING graph exactly
(same state VALUES -- 'IDLE' etc, not python-statemachine's lowercase-by-default `.id` --
see below), driven through the real, unmodified bind_standard_workflow_actions() from
standard_workflow.py, with a FakeDAQScan model shaped like the real DAQScan extension:
start_scan() with set_scan()-can-fail validation, stop_scan(), after_pause()/after_resume()
(the python-statemachine-native replacement for today's
`workflow.on(PAUSE, self._on_pause_triggered)` registration -- see below), and a
worker-simulated FINISHED transition.

--- State value vs id -----------------------------------------------------
python-statemachine's `.id` is always derived from the attribute name (lowercase, fixed --
confirmed empirically, `value=` doesn't change it). Existing tests/daq_scan.py compare
`workflow.state == 'RUNNING'` (uppercase, via StandardStates). So states are declared with
an explicit `value=StandardStates.RUNNING` etc., and ChartAdapter.state reads `.value`, not
`.id`, to preserve that comparison without touching any existing test.

--- after_pause()/after_resume() replace workflow.on(...) registration ----
Confirmed empirically: a method named after_<event>(self, event, source, target) defined
directly on the `model` object (not the StateMachine subclass) is called automatically by
python-statemachine's dispatcher, scoped correctly to that specific transition -- `start`
does NOT spuriously fire `after_resume` even though both start and resume land on
`running`. So DAQScan._on_pause_triggered/_on_resume_triggered rename to
after_pause/after_resume and connect_things() drops the `workflow.on(...)` calls entirely
-- two fewer lines than today, not more.

Requires: pip install python-statemachine (not a project dependency).
Run: python3 python_statemachine_daqscan_poc.py
"""
from statemachine import StateMachine, State
from statemachine.exceptions import TransitionNotAllowed
from qtpy import QtCore, QtWidgets

from pymodaq_gui.managers.action_manager import ActionManager
from pymodaq_gui.managers.workflow_manager import DEFAULT_WORKFLOW_NAME
from pymodaq_gui.managers.standard_workflow import (
    StandardStates, StandardTransitions, bind_standard_workflow_actions)


class StandardChart(StateMachine):
    """ python-statemachine analog of standard_workflow()'s graph -- same states, same
    five transitions, same (lack of a) START guard. """
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
    """ Same as python_statemachine_adapter.py's, plus `.name` for action_name_for()
    compatibility -- the only other thing bind_standard_workflow_actions()/
    bind_pause_action() touch beyond what was already confirmed. """
    state_changed = QtCore.Signal(object, object)
    revalidated = QtCore.Signal()

    def __init__(self, chart_cls, model, name: str = DEFAULT_WORKFLOW_NAME):
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


class FakeDAQScan:
    """ Shaped like the real DAQScan extension's relevant slice: start_scan()/stop_scan()
    with the same calling convention (self.adapter.trigger(NAME), same as today's
    self.workflow.trigger(NAME)), after_pause()/after_resume() instead of registered
    hooks, and connect_things() wiring bind_standard_workflow_actions() completely
    unmodified. No pause_scan()/on_pause_resume -- deleted for the same reason it was
    deleted from the real daq_scan.py (see earlier session): it added nothing over
    bind_toggle()'s bare trigger_any() default. """

    def __init__(self, action_manager, setup_ok: bool = True):
        self.setup_ok = setup_ok
        self.side_effects = []
        self.adapter = ChartAdapter(StandardChart, model=self)
        self.connect_things(action_manager)

    def connect_things(self, action_manager):
        bind_standard_workflow_actions(
            action_manager, self.adapter,
            on_start=self.start_scan, on_stop=self.stop_scan)

    def set_scan(self) -> bool:
        return self.setup_ok

    def start_scan(self) -> bool:
        if not self.set_scan():
            return False
        self.side_effects.append('start_scan setup ran')
        return True

    def stop_scan(self):
        self.side_effects.append('stop_scan cleanup ran')

    def after_pause(self, event, source, target):
        self.side_effects.append('after_pause: acquisition paused')

    def after_resume(self, event, source, target):
        self.side_effects.append('after_resume: acquisition running')

    def worker_reports_done(self):
        """ Same as the real thread_status()'s 'Scan_done' branch calling
        self.workflow.trigger(StandardTransitions.FINISHED) today. """
        self.adapter.trigger(StandardTransitions.FINISHED)


if __name__ == '__main__':
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    action_manager = ActionManager(toolbar=QtWidgets.QToolBar())

    daq_scan = FakeDAQScan(action_manager)
    adapter = daq_scan.adapter

    assert adapter.state == 'IDLE'
    assert action_manager.is_action_enabled('start')
    assert not action_manager.is_action_enabled('stop')

    action_manager.get_action('start').trigger()
    assert adapter.state == 'RUNNING'
    assert 'start_scan setup ran' in daq_scan.side_effects
    assert not action_manager.is_action_enabled('start')
    assert action_manager.is_action_enabled('stop')

    action_manager.get_action('pause').trigger()
    assert adapter.state == 'PAUSED'
    assert 'after_pause: acquisition paused' in daq_scan.side_effects

    action_manager.get_action('pause').trigger()
    assert adapter.state == 'RUNNING'
    assert 'after_resume: acquisition running' in daq_scan.side_effects

    action_manager.get_action('stop').trigger()
    assert adapter.state == 'STOPPING'
    assert 'stop_scan cleanup ran' in daq_scan.side_effects

    daq_scan.worker_reports_done()  # not a button -- simulates the real thread_status() path
    assert adapter.state == 'IDLE'
    assert action_manager.is_action_enabled('start')

    # set_scan() validation failure -- must NOT enter RUNNING (this was the real bug caught
    # earlier when porting workflow_manager.py's bind_transition contract)
    daq_scan.setup_ok = False
    action_manager.get_action('start').trigger()
    assert adapter.state == 'IDLE'

    print('Full daq_scan-shaped lifecycle OK, through unmodified '
         'bind_standard_workflow_actions(), against a python-statemachine chart.')
