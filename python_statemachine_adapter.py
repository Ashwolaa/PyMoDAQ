"""
Throwaway PoC -- not part of any package, not wired into anything.

The key result from exploring python-statemachine (see python_statemachine_poc.py,
STATEMACHINE_REVIEW.md): workflow_manager.py's bind_transition()/bind_toggle() don't
actually need a workflow_manager.Workflow instance -- they only ever call
.trigger()/.can_trigger()/.trigger_any()/.can_trigger_any() and connect to
.state_changed/.revalidated. Duck-type those onto a python-statemachine chart and
bind_transition()/bind_toggle() work COMPLETELY UNCHANGED -- no _sm variants needed,
confirmed below by importing the real functions from the package.

bind_enabled_to_states()/bind_enabled_to_transition() confirmed below too -- same story,
they only need `.state`/`.can_trigger()`, both already on ChartAdapter.

Deliberately NOT pursuing a WorkflowInspector equivalent: python-statemachine has its own
built-in graph introspection/diagram generation (Mermaid/Graphviz, see the `[diagrams]`
extra), which covers the same need differently and isn't required for the standard
start/stop/pause use case either way.

Requires: pip install python-statemachine (not a project dependency).
Run: python3 python_statemachine_adapter.py
"""
from statemachine import StateMachine, State
from statemachine.exceptions import TransitionNotAllowed
from qtpy import QtCore, QtWidgets

from pymodaq_gui.managers.workflow_manager import (
    bind_transition, bind_toggle, bind_enabled_to_states, bind_enabled_to_transition)


class DaqScanChart(StateMachine):
    idle = State(initial=True)
    running = State()
    paused = State()
    stopping = State()

    start = idle.to(running)
    pause = running.to(paused)
    resume = paused.to(running)
    stop = running.to(stopping) | paused.to(stopping)
    finished = stopping.to(idle) | running.to(idle)

    def after_transition(self, event, source, target):
        self.adapter.state_changed.emit(str(source.id), str(target.id))


class ChartAdapter(QtCore.QObject):
    """ Makes a python-statemachine chart duck-type as a workflow_manager.Workflow --
    only the surface bind_transition()/bind_toggle()/bind_enabled() actually touch. """
    state_changed = QtCore.Signal(object, object)
    revalidated = QtCore.Signal()

    def __init__(self, chart_cls, model):
        super().__init__()
        self.chart = chart_cls(model=model)
        self.chart.adapter = self  # so after_transition() above can reach us

    @property
    def state(self) -> str:
        # .configuration (plural: an OrderedSet of active states) is the non-deprecated
        # replacement for .current_state -- for a flat (non-parallel) chart it's always a
        # single element, but the plural shape is a live reminder that a compound/parallel
        # chart (e.g. a future sequencer port) can have more than one state active at once,
        # which this single-state `.state` property deliberately doesn't attempt to model.
        return str(next(iter(self.chart.configuration)).id)

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


class Model:
    def __init__(self):
        self.setup_ok = True

    def set_scan(self) -> bool:
        return self.setup_ok


if __name__ == '__main__':
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    model = Model()
    adapter = ChartAdapter(DaqScanChart, model)

    start_action = QtWidgets.QAction('Start')

    def on_start(*_):
        return model.set_scan()  # validation only -- bind_transition's wrapper auto-triggers

    bind_transition(start_action, adapter, 'start', click_slot=on_start)

    pause_action = QtWidgets.QAction('Pause')
    pause_action.setCheckable(True)
    bind_toggle(pause_action, adapter, 'pause', 'resume')

    assert start_action.isEnabled()
    start_action.trigger()
    assert adapter.state == 'running'
    assert pause_action.isEnabled() and not pause_action.isChecked()

    pause_action.trigger()
    assert adapter.state == 'paused' and pause_action.isChecked()
    pause_action.trigger()
    assert adapter.state == 'running' and not pause_action.isChecked()

    # bind_enabled_to_states() / bind_enabled_to_transition() -- same story: only need
    # .state / .can_trigger(), both already on ChartAdapter, so also unmodified.
    ini_positions_widget = QtWidgets.QPushButton('ini_positions')
    bind_enabled_to_states(ini_positions_widget, adapter, ['idle'])
    assert not ini_positions_widget.isEnabled()  # we're in 'running', not 'idle'

    stop_widget = QtWidgets.QPushButton('stop')
    bind_enabled_to_transition(stop_widget, adapter, 'stop')
    assert stop_widget.isEnabled()  # 'stop' is legal from 'running'

    adapter.trigger('pause')
    adapter.trigger('resume')
    adapter.trigger('stop')
    assert not stop_widget.isEnabled()  # 'stop' no longer legal once in 'stopping'
    adapter.trigger('finished')
    assert ini_positions_widget.isEnabled()  # back to 'idle'

    print('bind_transition()/bind_toggle()/bind_enabled_to_states()/'
         'bind_enabled_to_transition(), all unmodified, work against a python-statemachine '
         'chart via ChartAdapter.')
