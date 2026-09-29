"""
Throwaway PoC -- not part of any package, not wired into anything.

Exercises the REAL, committed daq_scan.py methods (DAQScan.can_start, DAQScan.after_pause,
DAQScan.after_resume) against the real, shared StandardChart/ChartAdapter, rather than a
reimplementation -- imported directly from
packages/pymodaq/src/pymodaq/extensions/scan/daq_scan.py and
packages/pymodaq_gui/src/pymodaq_gui/managers/statemachine_workflow.py.

Full Dashboard + mock-hardware preset instantiation of the real DAQScan extension is a
bigger undertaking than a single PoC (docks, toolbars, hardware managers all get built in
CustomExt.__init__) and this sandbox has no real display to watch it in anyway. So this
stubs out only the Dashboard-dependent pieces, the same way the existing test suite's
`scan_acquisition` fixture (packages/pymodaq/tests/extensions/daq_scan_test.py) already
stubs DAQScan for DAQScanAcquisition tests -- not a new pattern, following precedent.

Unrelated, pre-existing environment gap worked around here for import purposes only (NOT
part of the actual fix): pymodaq.extensions eagerly imports the sequencer, which imports
PySide6.QtStateMachine, not installed in this sandbox. Stubbed via sys.modules so
daq_scan.py itself can be imported; irrelevant to anything tested here.

Run for real, with a display, on a machine with PySide6's QtStateMachine actually
installed: no stubbing needed, this whole block can be deleted.

Requires: pip install python-statemachine.
Run: python3 python_statemachine_daqscan_live_test.py
"""
import sys
import types

for name in ('QStateMachine', 'QState', 'QFinalState', 'QSignalTransition',
            'QAbstractTransition', 'QHistoryState'):
    pass
_fake_qsm = types.ModuleType('PySide6.QtStateMachine')
for _name in ('QStateMachine', 'QState', 'QFinalState', 'QSignalTransition',
             'QAbstractTransition', 'QHistoryState'):
    setattr(_fake_qsm, _name, type(_name, (), {'SignalEvent': type('SignalEvent', (), {})}))
sys.modules.setdefault('PySide6.QtStateMachine', _fake_qsm)

from qtpy import QtCore, QtWidgets
from pymodaq_gui.managers.action_manager import ActionManager
from pymodaq_gui.managers.standard_workflow import bind_standard_workflow_actions

# The real thing, imported directly -- not reimplemented.
from pymodaq.extensions.scan.daq_scan import DAQScan
from pymodaq_gui.managers.statemachine_workflow import StandardChart, ChartAdapter


class FakeExperimentManager:
    def __init__(self, entry_applied: bool = False):
        self.entry_applied = entry_applied


class RealDAQScanStandIn(QtCore.QObject):
    """ Instantiates DAQScan's actual __init__ logic that this PoC cares about, without
    going through CustomExt.__init__'s full dock/toolbar/hardware setup. Reuses the real
    can_start/after_pause/after_resume methods via composition + explicit binding, since
    subclassing DAQScan itself would still need to call super().__init__() (CustomExt). """

    command_daq_signal = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self.experiment_manager = FakeExperimentManager(entry_applied=False)
        self.status_manager = type('S', (), {'set_permanent_status': lambda self, s: None})()
        # bind the REAL DAQScan methods onto this stand-in
        self.can_start = DAQScan.can_start.__get__(self)
        self.after_pause = DAQScan.after_pause.__get__(self)
        self.after_resume = DAQScan.after_resume.__get__(self)


if __name__ == '__main__':
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    model = RealDAQScanStandIn()
    # real StandardChart, real ChartAdapter, real DAQScan.can_start as the guard
    workflow = ChartAdapter(StandardChart, model=model, guards={'start': model.can_start})

    action_manager = ActionManager(toolbar=QtWidgets.QToolBar())
    bind_standard_workflow_actions(
        action_manager, workflow, on_start=lambda: True, on_stop=lambda: None)

    pause_events = []
    model.command_daq_signal.connect(lambda cmd: pause_events.append(cmd))

    assert workflow.state == 'IDLE'
    assert not action_manager.is_action_enabled('start'), (
        "real can_start() guard should refuse: no experiment entry applied yet")

    model.experiment_manager.entry_applied = True
    workflow.revalidate()  # same call daq_scan.py's do_things_after_experiment_set() makes
    assert action_manager.is_action_enabled('start'), "guard should now allow start"

    action_manager.get_action('start').trigger()
    assert workflow.state == 'RUNNING'

    action_manager.get_action('pause').trigger()
    assert workflow.state == 'PAUSED'
    assert len(pause_events) == 1, "real after_pause() should have emitted command_daq_signal"

    action_manager.get_action('pause').trigger()
    assert workflow.state == 'RUNNING'
    assert len(pause_events) == 2, "real after_resume() should have emitted command_daq_signal"

    action_manager.get_action('stop').trigger()
    assert workflow.state == 'STOPPING'

    print('Real StandardChart + real DAQScan.can_start/after_pause/after_resume (guard via '
         'ChartAdapter, not cond=), driven through unmodified bind_standard_workflow_actions(), '
         'all correct.')
