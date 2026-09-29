"""
Throwaway PoC -- not part of any package, not wired into anything.

Explores replacing workflow_manager.py's engine with python-statemachine
(github.com/fgmacedo/python-statemachine), per the suggestion on PR #1219:
https://github.com/PyMoDAQ/PyMoDAQ/pull/1219#issuecomment-5893125212

Requires: pip install python-statemachine (not a project dependency).

--- Why `start`/`pause`/etc. below have NO `cond=` -----------------------
Today's standard_workflow() doesn't put set_scan() on the START transition
as a `guard` either -- `add_transition(START, [IDLE], RUNNING)` is
unguarded. That's deliberate: `cond=` is re-evaluated every time
`allowed_events` is checked, which bind_transition-equivalent UI syncing
does on every state_changed/revalidate (i.e. constantly, including on
every UI resync). set_scan() has real side effects -- creates h5 nodes,
pops message boxes -- so it must NOT run as a `cond=`. It belongs where
it already lives: inside start_scan(), run once at click/call time.

--- Which resolves the earlier click_slot "return False" wart -----------
workflow_manager.py needed click_slot to return False because
bind_transition auto-fires trigger() *after* the callback, generically,
for any callback. Here there's no such generic wrapper: start_scan() owns
calling self.chart.start() itself, exactly once, only when it decides to.
Nothing auto-retriggers behind its back, so there's nothing to veto.
"""
from statemachine import StateMachine, State
from statemachine.exceptions import TransitionNotAllowed
from qtpy import QtCore


class ChartQt(QtCore.QObject):
    """ The Qt-facing half, held by composition (see STATEMACHINE_REVIEW.md
    for why StateMachine can't be multiply-inherited alongside QObject --
    metaclass conflict, confirmed empirically). One generic signal plus
    two specific ones, mirroring daq_scan.py's real
    _on_pause_triggered/_on_resume_triggered hooks (which today emit
    command_daq_signal with ThreadCommand('pause_acquisition', ...)). """
    state_changed = QtCore.Signal(str, str)  # old, new -- fires on every transition
    paused = QtCore.Signal()
    resumed = QtCore.Signal()


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

    def __init__(self, model, qt: ChartQt):
        self.qt = qt
        super().__init__(model=model)

    # state-specific hooks fire BEFORE the generic one below (confirmed
    # empirically) -- same ordering workflow_manager.py's Workflow.trigger()
    # gives today (transition/exit hooks, commit, enter hooks, THEN
    # state_changed.emit()).
    def on_enter_paused(self):
        self.qt.paused.emit()

    def on_enter_running(self, source):
        if str(source.id) == 'paused':
            self.qt.resumed.emit()

    def after_transition(self, event, source, target):
        self.qt.state_changed.emit(str(source.id), str(target.id))


class Model:
    """ Stand-in for DAQScan itself: `model=` is any plain object. These
    three mirror daq_scan.py's real start_scan/stop_scan/pause_scan --
    same shape, same "also called directly, not just from a button"
    requirement, same set_scan()-can-fail case. """

    def __init__(self, setup_ok: bool = True):
        self.setup_ok = setup_ok
        self.qt = ChartQt()
        self.chart = DaqScanChart(model=self, qt=self.qt)

    def set_scan(self) -> bool:
        """ Stand-in for the real validation -- can fail. """
        return self.setup_ok

    def start_scan(self) -> bool:
        if not self.set_scan():
            return False  # no self.chart.start() call at all -- stay idle
        # ... real setup would go here (h5 node, live view init, ...) ...
        self.chart.start()
        # ... real post-transition side effects would go here ...
        return True

    def stop_scan(self):
        self.chart.stop()  # unconditional, like today's stop_scan()

    def pause_scan(self):
        """ Toggle: `python-statemachine` has no trigger_any() equivalent,
        so the toggle direction has to be picked explicitly -- arguably
        clearer than workflow_manager.py's implicit "whichever of these
        two is legal" trigger_any(RESUME, PAUSE). """
        if 'pause' in [str(e) for e in self.chart.allowed_events]:
            self.chart.pause()
        else:
            self.chart.resume()


if __name__ == '__main__':
    model = Model()

    received = []
    model.qt.state_changed.connect(lambda o, n: received.append(f'state_changed {o}->{n}'))
    model.qt.paused.connect(lambda: received.append('paused'))
    model.qt.resumed.connect(lambda: received.append('resumed'))

    assert model.start_scan() is True
    assert model.chart.current_state.id == 'running'

    model.pause_scan()
    assert model.chart.current_state.id == 'paused'
    model.pause_scan()
    assert model.chart.current_state.id == 'running'

    print('Qt signals received so far:', received)
    assert received == [
        'state_changed idle->running',
        'paused', 'state_changed running->paused',
        'resumed', 'state_changed paused->running',
    ]

    model.stop_scan()
    assert model.chart.current_state.id == 'stopping'
    model.chart.finished()
    assert model.chart.current_state.id == 'idle'
    print('full lifecycle OK, reached:', model.chart.current_state.id)

    model.setup_ok = False
    assert model.start_scan() is False  # refused cleanly, no exception needed
    assert model.chart.current_state.id == 'idle'
    print('set_scan() failure correctly refused, still:', model.chart.current_state.id)

    # direct/programmatic call bypassing any button -- still works, same
    # as daq_scan.py's do_scan()/stop()/start_scan_batch() calling these
    # methods straight, not through a click
    model.setup_ok = True
    model.start_scan()
    try:
        model.chart.start()  # illegal from RUNNING -- no cond= needed, state alone blocks it
    except TransitionNotAllowed as e:
        print('direct re-start correctly refused:', e)
