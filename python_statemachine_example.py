"""
Example: DaqScanChart (python-statemachine) live demo -- NOT part of the
codebase. The python-statemachine analog of workflow_inspector_example.py,
for comparing the two engines side by side.

Shows a real toolbar (Start/Stop/Pause) driving python_statemachine_poc.py's
DaqScanChart, next to a live state label + transition log fed by the
ChartQt signals from that PoC. Click the toolbar actions and watch both
update.

Unlike workflow_inspector_example.py, there's no WorkflowInspector
equivalent here -- python-statemachine doesn't expose a flat, introspectable
transition table the way workflow_manager.Workflow does (its transitions
live as descriptors on the class, resolved through its metaclass), so a
comparable inspector widget would need its own, different implementation.
This demo substitutes a plain log instead.

Also: this graph can't be extended at runtime the way workflow_inspector_
example.py extends the standard template with an ad hoc 'fail' transition
(`workflow.add_transition('fail', ['RUNNING'], 'ERROR')`, two lines, no
subclass). DaqScanChart's graph is fixed at class-definition time -- adding
a state/transition means subclassing DaqScanChart, not mutating an
instance. Concrete illustration of the declarative-vs-data-driven gap
covered in STATEMACHINE_REVIEW.md.

Requires: pip install python-statemachine (not a project dependency).
Run (needs a real display -- no QT_QPA_PLATFORM=offscreen this time):
    python3 python_statemachine_example.py
"""
import sys
from qtpy.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QWidget, QVBoxLayout, QLabel, QListWidget)

from pymodaq_gui.managers.action_manager import ActionManager

from python_statemachine_poc import Model


def bind_transition_sm(widget, model, event_name: str, signal_name: str = 'triggered'):
    """ python-statemachine analog of workflow_manager.bind_transition(): click ->
    getattr(chart, event_name)(); enabled kept synced to allowed_events. No click_slot/
    veto contract needed here -- see python_statemachine_poc.py's module docstring for why:
    the model method (start_scan() etc.) already owns deciding whether to call the chart
    event at all, so there's nothing left for a generic wrapper to auto-fire or veto. """
    def click_slot(*_):
        # 'start' goes through start_scan() for its set_scan()-can-fail validation; the
        # rest have no validation of their own, so the chart event can be called directly.
        if event_name == 'start':
            model.start_scan()
        else:
            getattr(model.chart, event_name)()

    def sync_slot(*_):
        widget.setEnabled(event_name in [str(e) for e in model.chart.allowed_events])

    getattr(widget, signal_name).connect(click_slot)
    model.qt.state_changed.connect(sync_slot)
    sync_slot()


def bind_toggle_sm(widget, model, off_event: str, on_event: str, signal_name: str = 'triggered'):
    """ python-statemachine analog of bind_toggle(): click -> pause_scan(), which itself
    (see python_statemachine_poc.py) picks whichever of off_event/on_event is currently
    legal -- no trigger_any()-style helper needed, one `if` does it directly. """
    def click_slot(*_):
        model.pause_scan()

    def sync_slot(*_):
        allowed = [str(e) for e in model.chart.allowed_events]
        widget.setEnabled(off_event in allowed or on_event in allowed)
        widget.setChecked(on_event in allowed)

    getattr(widget, signal_name).connect(click_slot)
    model.qt.state_changed.connect(sync_slot)
    sync_slot()


app = QApplication.instance() or QApplication(sys.argv)

mainwindow = QMainWindow()
mainwindow.setWindowTitle('python-statemachine example')

toolbar = QToolBar('Scan')
mainwindow.addToolBar(toolbar)
action_manager = ActionManager(toolbar=toolbar)

model = Model()

start_action = action_manager.add_action('start', 'Start', 'motion_play', 'Start')
bind_transition_sm(start_action, model, 'start')

stop_action = action_manager.add_action('stop', 'Stop', 'stop_circle', 'Stop')
bind_transition_sm(stop_action, model, 'stop')

pause_action = action_manager.add_action('pause', 'Pause', 'pause_circle', 'Pause/resume',
                                         checkable=True)
bind_toggle_sm(pause_action, model, 'pause', 'resume')

toolbar.addSeparator()
finished_action = action_manager.add_action('finished', 'Finished (simulate worker done)')
bind_transition_sm(finished_action, model, 'finished')

state_label = QLabel()
log = QListWidget()


def refresh_label(*_):
    state_label.setText(f'State: {model.chart.current_state.id}')


def log_transition(old, new):
    log.addItem(f'{old} -> {new}')
    log.scrollToBottom()


model.qt.state_changed.connect(refresh_label)
model.qt.state_changed.connect(log_transition)
model.qt.paused.connect(lambda: log.addItem('  (paused signal)'))
model.qt.resumed.connect(lambda: log.addItem('  (resumed signal)'))
refresh_label()

central = QWidget()
layout = QVBoxLayout()
layout.addWidget(state_label)
layout.addWidget(log)
central.setLayout(layout)

mainwindow.setCentralWidget(central)
mainwindow.resize(500, 400)
mainwindow.show()

sys.exit(app.exec())
