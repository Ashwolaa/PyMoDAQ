"""
DRAFT — WorkflowInspector analog for a ChartAdapter. Not wired in yet.

Uses python-statemachine's own `diagrams` extra (MermaidGraphMachine) instead
of hand-maintaining a state/transition table: it derives a live diagram from
the chart's own graph, current state highlighted. Paste the text into
https://mermaid.live to see it -- no QWebEngineView pulled in here.

Requires: pip install python-statemachine[diagrams] (packages/pymodaq_gui[statemachine-diagrams]).
"""
from qtpy import QtWidgets

from statemachine.contrib.diagram import MermaidGraphMachine

from pymodaq_gui.managers.statemachine_workflow import ChartAdapter


class StatemachineInspector(QtWidgets.QWidget):
    """ Read-only debug view: live Mermaid source, current state highlighted,
    refreshed on every state_changed/revalidated. """

    def __init__(self, adapter: ChartAdapter, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.adapter = adapter
        self._mermaid = MermaidGraphMachine(adapter.chart)

        self.setWindowTitle(f"Statemachine inspector -- {adapter.name}")

        self._state_label = QtWidgets.QLabel()
        self._state_label.setStyleSheet('font-weight: bold; font-size: 12pt;')

        self._text = QtWidgets.QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)

        hint = QtWidgets.QLabel("Paste into https://mermaid.live to see the flowchart.")
        hint.setStyleSheet('color: gray;')

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._state_label)
        layout.addWidget(hint)
        layout.addWidget(self._text)
        self.setLayout(layout)

        adapter.state_changed.connect(self.refresh)
        adapter.revalidated.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        self._state_label.setText(f"State: {self.adapter.state}")
        self._text.setPlainText(self._mermaid.get_mermaid())
