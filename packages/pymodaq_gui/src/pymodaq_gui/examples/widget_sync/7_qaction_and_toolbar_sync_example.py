"""
Example 7: QAction Binding and ValueSync.bind_parameter()
===========================================================

Demonstrates two new features of widget_sync:

1. **QAction binding** — QAction is a QObject (not a QWidget), and is now
   supported everywhere a QObject is accepted. Useful for toolbar buttons,
   menu items, and checkable toolbar actions.

2. **ValueSync.bind_parameter()** — Binds a single pyqtgraph Parameter to a
   ValueSync. Complements DictSync.bind_parameter() for the simple one-to-one
   case (one parameter ↔ one toolbar widget).

Motivation
----------
In PyMoDAQ control modules (DAQ_Viewer, DAQ_Move, ...) several settings are
exposed both in the settings tree (for presets / serialisation) and in the
toolbar (for daily convenience). Keeping them in sync used to require manual
boilerplate (blockSignals + command signals). With these two additions, a single
binding per pair replaces 4 touch-points of code.

The example shows a simplified DAQ_Viewer-like window with:
- A toolbar carrying a spinbox, a combobox, and a checkable action
- A parameter tree carrying the same three settings
- Both staying fully in sync via ValueSync.bind_parameter() and
  a DictSync with QAction support

Run
---
python -m pymodaq_gui.examples.widget_sync.7_qaction_and_toolbar_sync_example
"""

import sys

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QComboBox, QToolBar, QAction, QGroupBox,
    QStatusBar,
)

from pymodaq_gui.parameter import Parameter, ParameterTree
from pymodaq_gui.utils.widget_sync import ValueSync, DictSync


# ---------------------------------------------------------------------------
# Parameter tree definition  (mimics pymodaq's main_settings)
# ---------------------------------------------------------------------------

PARAMS = [
    {'title': 'Acquisition', 'name': 'acquisition', 'type': 'group',
     'children': [
         {'title': 'N average:', 'name': 'Naverage',
          'type': 'int', 'value': 1, 'min': 1},
         {'title': 'Acq mode:', 'name': 'acq_mode',
          'type': 'list', 'limits': ['Average', 'Sum'], 'value': 'Average'},
         {'title': 'Show averaging:', 'name': 'show_averaging',
          'type': 'bool', 'value': False},
     ]},
]


class ToolbarSettingsDemo(QMainWindow):
    """
    Minimal window with a toolbar and a settings tree, kept in sync
    without any manual blockSignals or command-signal plumbing.

    Three settings are mirrored between the toolbar and the parameter tree:
      • Naverage      (int)    — QSpinBox  ↔  ValueSync  ↔  Parameter
      • acq_mode      (str)    — QComboBox ↔  ValueSync  ↔  Parameter
      • show_averaging (bool)  — QAction   ↔  ValueSync  ↔  Parameter
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Example 7: QAction + ValueSync.bind_parameter()")
        self.resize(800, 500)
        self.statusBar().showMessage("Ready")

        # Build parameter tree
        self.settings = Parameter.create(
            name='settings', type='group', children=PARAMS
        )

        # Build UI
        self._setup_toolbar()
        self._setup_central()

        # Wire everything up — the whole point of this example
        self._bind_toolbar_to_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_toolbar(self):
        tb = QToolBar("Acquisition")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addWidget(QLabel(" N avg: "))

        self._naverage_sb = QSpinBox()
        self._naverage_sb.setRange(1, 1000)
        self._naverage_sb.setFixedWidth(60)
        self._naverage_sb.setToolTip("Number of acquisitions to accumulate")
        tb.addWidget(self._naverage_sb)

        tb.addSeparator()
        tb.addWidget(QLabel(" Mode: "))

        self._acq_mode_cb = QComboBox()
        self._acq_mode_cb.addItems(['Average', 'Sum'])
        self._acq_mode_cb.setFixedWidth(90)
        self._acq_mode_cb.setToolTip("Accumulation mode")
        tb.addWidget(self._acq_mode_cb)

        tb.addSeparator()

        # QAction — now fully supported in widget_sync (QObject, not QWidget)
        self._show_avg_action = QAction("Show steps", self)
        self._show_avg_action.setCheckable(True)
        self._show_avg_action.setToolTip(
            "Show each accumulation step as it builds up"
        )
        tb.addAction(self._show_avg_action)

    def _setup_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # Parameter tree (left)
        tree_box = QGroupBox("Settings tree (canonical state)")
        tree_layout = QVBoxLayout(tree_box)
        self._param_tree = ParameterTree()
        self._param_tree.setParameters(self.settings, showTop=False)
        tree_layout.addWidget(self._param_tree)
        layout.addWidget(tree_box, 1)

        # Status panel (right) — shows current sync values
        status_box = QGroupBox("Current sync values")
        status_layout = QVBoxLayout(status_box)
        status_layout.setAlignment(Qt.AlignTop)
        self._status_labels = {}
        for key, label in [
            ('Naverage', 'N average:'),
            ('acq_mode', 'Acq mode:'),
            ('show_averaging', 'Show steps:'),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"<b>{label}</b>"))
            lbl = QLabel("—")
            lbl.setMinimumWidth(120)
            row.addWidget(lbl)
            self._status_labels[key] = lbl
            status_layout.addLayout(row)

        status_layout.addStretch()
        note = QLabel(
            "<small>All three sources (toolbar widget, QAction, settings tree)<br>"
            "stay in sync automatically — zero manual blockSignals().</small>"
        )
        note.setWordWrap(True)
        status_layout.addWidget(note)
        layout.addWidget(status_box, 1)

    # ------------------------------------------------------------------
    # Binding — the key part of this example
    # ------------------------------------------------------------------

    def _bind_toolbar_to_settings(self):
        """
        Single method that owns all toolbar ↔ settings-tree bindings.

        Pattern:
          toolbar widget  ↔  ValueSync  ↔  settings Parameter
                                ↑
                         ValueSync.bind_parameter()  (new in this PR)

        For QAction the only difference is that we provide
        signal/getter/setter explicitly (toggled / isChecked / setChecked)
        because QAction is a QObject, not a QWidget.
        """
        acq = self.settings.child('acquisition')

        # --- 1. Naverage: QSpinBox ↔ ValueSync ↔ Parameter ---
        self._naverage_sync = ValueSync(
            initial_value=acq['Naverage']
        )
        self._naverage_sync.bind(
            self._naverage_sb,
            signal=self._naverage_sb.valueChanged,
            getter=self._naverage_sb.value,
            setter=self._naverage_sb.setValue,
            init_from='sync',
        )
        self._naverage_sync.bind_parameter(
            acq.child('Naverage'), init_from='sync'
        )
        self._naverage_sync.value_changed.connect(
            lambda v: self._update_status('Naverage', v)
        )

        # --- 2. acq_mode: QComboBox ↔ ValueSync ↔ Parameter ---
        self._acq_mode_sync = ValueSync(
            initial_value=acq['acq_mode']
        )
        self._acq_mode_sync.bind(
            self._acq_mode_cb,
            signal=self._acq_mode_cb.currentTextChanged,
            getter=self._acq_mode_cb.currentText,
            setter=self._acq_mode_cb.setCurrentText,
            init_from='sync',
        )
        self._acq_mode_sync.bind_parameter(
            acq.child('acq_mode'), init_from='sync'
        )
        self._acq_mode_sync.value_changed.connect(
            lambda v: self._update_status('acq_mode', v)
        )

        # --- 3. show_averaging: QAction ↔ ValueSync ↔ Parameter ---
        #    QAction is a QObject — bind() now accepts it directly.
        self._show_avg_sync = ValueSync(
            initial_value=acq['show_averaging']
        )
        self._show_avg_sync.bind(
            self._show_avg_action,
            signal=self._show_avg_action.toggled,
            getter=self._show_avg_action.isChecked,
            setter=self._show_avg_action.setChecked,
            init_from='sync',
        )
        self._show_avg_sync.bind_parameter(
            acq.child('show_averaging'), init_from='sync'
        )
        self._show_avg_sync.value_changed.connect(
            lambda v: self._update_status('show_averaging', v)
        )

        # Initialise status labels
        self._update_status('Naverage', acq['Naverage'])
        self._update_status('acq_mode', acq['acq_mode'])
        self._update_status('show_averaging', acq['show_averaging'])

    def _update_status(self, key: str, value):
        lbl = self._status_labels.get(key)
        if lbl is not None:
            lbl.setText(str(value))
        self.statusBar().showMessage(f"{key} changed → {value}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = ToolbarSettingsDemo()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
