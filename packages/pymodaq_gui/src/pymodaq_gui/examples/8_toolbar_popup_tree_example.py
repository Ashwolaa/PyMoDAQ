"""
Example 8: ToolbarPopupTree
===========================

Demonstrates :class:`~pymodaq_gui.utils.widgets.toolbar_popup.ToolbarPopupTree`:
a toolbar button that reveals a floating :class:`ParameterTree` panel when
clicked.

Motivation
----------
Control modules (DAQ_Viewer, DAQ_Move, …) expose a settings tree that is
canonical (serialisable, works headlessly) and a toolbar for daily convenience.
The previous PR (example 7) showed how :class:`~pymodaq_gui.utils.widget_sync.ValueSync`
keeps a handful of frequently-touched parameters in sync with inline toolbar
widgets (spinboxes, comboboxes, checkable actions).

For *groups* of less-frequently-touched settings the inline approach scales
badly — the toolbar becomes crowded, and every new parameter requires a
matching widget plus a sync binding.

:class:`ToolbarPopupTree` solves this with a **third tier**:

  * **Tier 1 — inline widgets** (QSpinBox / QComboBox / QAction)
    For the 2-3 parameters touched every few seconds.
    Synced via ``ValueSync.bind_parameter()``.

  * **Tier 2 — popup sub-tree buttons**  ← this example
    A single toolbar button reveals a floating ParameterTree panel scoped
    to a sub-group.  Because the tree IS the canonical parameter object (not
    a copy), **no synchronisation is needed**.  Edits are live immediately.

  * **Tier 3 — full settings panel** (show_settings action)
    For everything, including read-only and advanced parameters.

The example window
------------------
The window mimics a simplified DAQ_Viewer with:

  * Inline toolbar widgets for Naverage and acq_mode (tier 1, via ValueSync)
  * A "Timing ▾" popup button exposing wait_time and refresh_time (tier 2)
  * A "Save ▾"   popup button exposing the saver_settings group  (tier 2)
  * A full settings tree on the right (tier 3, read-only in this demo)

Try:
  - Changing wait_time in the popup → it updates immediately in the full tree
  - Changing Naverage in the spinbox → it updates in the full tree
  - Changing any value in the full tree → popup and spinbox stay in sync

Run
---
python -m pymodaq_gui.examples.8_toolbar_popup_tree_example
"""

import sys

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QComboBox, QToolBar, QGroupBox, QStatusBar,
)

from pymodaq_gui.parameter import Parameter, ParameterTree
from pymodaq_gui.utils.widget_sync import ValueSync
from pymodaq_gui.utils.widgets.toolbar_popup import ToolbarPopupTree


# ---------------------------------------------------------------------------
# Fake parameter tree (mirrors what DAQ_Viewer uses)
# ---------------------------------------------------------------------------

PARAMS = [
    {'title': 'Main Settings', 'name': 'main_settings', 'type': 'group',
     'children': [
         {'title': 'N Acquisitions:', 'name': 'Naverage',
          'type': 'int', 'value': 1, 'min': 1},
         {'title': 'Acq. mode:', 'name': 'acq_mode',
          'type': 'list', 'limits': ['Average', 'Sum'], 'value': 'Average'},
         {'title': 'Wait time (ms):', 'name': 'wait_time',
          'type': 'int', 'value': 0, 'min': 0},
         {'title': 'Refresh time (ms):', 'name': 'refresh_time',
          'type': 'float', 'value': 50., 'min': 0.},
         {'title': 'Show data:', 'name': 'show_data',
          'type': 'bool', 'value': True},
     ]},
    {'title': 'Saver Settings', 'name': 'saver_settings', 'type': 'group',
     'children': [
         {'title': 'Save continuously:', 'name': 'do_save',
          'type': 'bool', 'value': False},
         {'title': 'Base name:', 'name': 'base_name',
          'type': 'str', 'value': 'Data'},
         {'title': 'Saved so far:', 'name': 'N_saved',
          'type': 'int', 'value': 0, 'readonly': True},
     ]},
]


# ---------------------------------------------------------------------------
# Demo window
# ---------------------------------------------------------------------------

class PopupTreeDemo(QMainWindow):
    """
    Three-tier toolbar ↔ settings architecture:

      Tier 1 — inline QSpinBox / QComboBox (via ValueSync.bind_parameter)
      Tier 2 — ToolbarPopupTree buttons ("Timing ▾", "Save ▾")
      Tier 3 — full ParameterTree panel (show_settings action, right side)
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Example 8: ToolbarPopupTree')
        self.resize(900, 500)

        self.settings = Parameter.create(
            name='settings', type='group', children=PARAMS,
        )

        self._setup_toolbar()
        self._setup_central()
        self._bind_toolbar_to_settings()  # tier-1 syncs only

        self.settings.sigTreeStateChanged.connect(self._on_any_change)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_toolbar(self):
        tb = QToolBar('Controls')
        tb.setMovable(False)
        self.addToolBar(tb)

        # --- Tier 1: inline widgets ---
        tb.addWidget(QLabel(' N avg: '))

        self._naverage_sb = QSpinBox()
        self._naverage_sb.setRange(1, 1000)
        self._naverage_sb.setFixedWidth(60)
        self._naverage_sb.setToolTip('Number of acquisitions to accumulate')
        tb.addWidget(self._naverage_sb)

        tb.addSeparator()
        tb.addWidget(QLabel(' Mode: '))

        self._acq_mode_cb = QComboBox()
        self._acq_mode_cb.addItems(['Average', 'Sum'])
        self._acq_mode_cb.setFixedWidth(90)
        tb.addWidget(self._acq_mode_cb)

        tb.addSeparator()

        # --- Tier 2: popup sub-tree buttons ---
        ms = self.settings.child('main_settings')

        timing_btn = ToolbarPopupTree(
            param=ms,          # show the whole main_settings group in the popup
            title='Settings',
            icon_name='settings',
            min_width=280,
        )
        tb.addWidget(timing_btn)

        tb.addSeparator()

        save_btn = ToolbarPopupTree(
            param=self.settings.child('saver_settings'),
            title='Save',
            icon_name='save',
            min_width=260,
        )
        tb.addWidget(save_btn)

    def _setup_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # Full settings tree (tier 3) on the right
        box = QGroupBox('Full settings tree (canonical state — tier 3)')
        box_layout = QVBoxLayout(box)
        self._full_tree = ParameterTree()
        self._full_tree.setParameters(self.settings, showTop=False)
        box_layout.addWidget(self._full_tree)
        layout.addWidget(box)

        # Status panel on the left
        status_box = QGroupBox('Last change')
        status_layout = QVBoxLayout(status_box)
        status_layout.setAlignment(Qt.AlignTop)
        self._status_lbl = QLabel('—')
        self._status_lbl.setWordWrap(True)
        status_layout.addWidget(self._status_lbl)
        status_layout.addStretch()
        note = QLabel(
            '<small>'
            '<b>Tier 1</b> (inline widgets): Naverage, acq_mode — synced via ValueSync.<br><br>'
            '<b>Tier 2</b> (popup buttons): "Settings ▾" shows main_settings group;<br>'
            '"Save ▾" shows saver_settings group.<br>'
            'No extra sync — the popup tree IS the canonical Parameter.<br><br>'
            '<b>Tier 3</b> (full tree): this panel — everything visible.'
            '</small>'
        )
        note.setWordWrap(True)
        status_layout.addWidget(note)
        layout.addWidget(status_box)

    # ------------------------------------------------------------------
    # Tier-1 bindings (ValueSync) — only for the inline widgets
    # ------------------------------------------------------------------

    def _bind_toolbar_to_settings(self):
        ms = self.settings.child('main_settings')

        self._naverage_sync = ValueSync(initial_value=ms['Naverage'])
        self._naverage_sync.bind(
            self._naverage_sb,
            signal=self._naverage_sb.valueChanged,
            getter=self._naverage_sb.value,
            setter=self._naverage_sb.setValue,
            init_from='sync',
        )
        self._naverage_sync.bind_parameter(ms.child('Naverage'), init_from='sync')

        self._acq_mode_sync = ValueSync(initial_value=ms['acq_mode'])
        self._acq_mode_sync.bind(
            self._acq_mode_cb,
            signal=self._acq_mode_cb.currentTextChanged,
            getter=self._acq_mode_cb.currentText,
            setter=self._acq_mode_cb.setCurrentText,
            init_from='sync',
        )
        self._acq_mode_sync.bind_parameter(ms.child('acq_mode'), init_from='sync')

    # ------------------------------------------------------------------
    # Status feedback
    # ------------------------------------------------------------------

    def _on_any_change(self, root, changes):
        for param, change, value in changes:
            if change == 'value':
                self._status_lbl.setText(
                    f'<b>{param.name()}</b> → {value}'
                )
                self.statusBar().showMessage(f'{param.name()} changed → {value}')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = PopupTreeDemo()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
