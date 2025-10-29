"""
Test example for the compact move widget with real DAQ_Move modules.
"""

import sys
from qtpy import QtWidgets, QtCore
from qtpy.QtCore import QThread

from pymodaq_gui.utils import DockArea, Dock
from pymodaq.control_modules.daq_move import DAQ_Move
from pymodaq.utils.gui_utils.compact_move_widget import CompactMoveManager


class CompactMoveExample(QtWidgets.QMainWindow):
    """Example application to test the compact move widget"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Compact Move Widget Test")
        self.resize(1300, 800)

        # Create main splitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.setCentralWidget(splitter)

        # Right side: DockArea for full module widgets (create first)
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_widget.setLayout(right_layout)

        self.dockarea = DockArea()
        right_layout.addWidget(self.dockarea)

        splitter.addWidget(right_widget)

        # Left side: Compact move manager
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout()
        left_widget.setLayout(left_layout)

        info_label = QtWidgets.QLabel(
            "<h2>Compact Move Manager</h2>"
            "<p>This shows actuators in a compact toolbar format.</p>"
            "<p><b>Test these buttons:</b></p>"
            "<ul>"
            "<li><b>Init:</b> Click to initialize the module (LED turns green)</li>"
            "<li><b>Show Widget:</b> Click to show/hide the full actuator widget on the right</li>"
            "<li><b>Settings:</b> Click to toggle settings tree visibility</li>"
            "<li><b>Close:</b> Click to remove the module</li>"
            "<li><b>Add Actuator:</b> Click to add a new actuator module</li>"
            "</ul>"
        )
        info_label.setWordWrap(True)
        left_layout.addWidget(info_label)

        # Create the compact move manager
        self.compact_manager = CompactMoveManager(dockarea=self.dockarea)
        self.compact_manager.add_move_requested.connect(self._on_add_move_requested)
        left_layout.addWidget(self.compact_manager)

        left_widget.setMaximumWidth(600)
        splitter.addWidget(left_widget)

        # Set splitter proportions (right side is index 0, left side is index 1)
        splitter.setStretchFactor(0, 3)  # Right side (dockarea)
        splitter.setStretchFactor(1, 1)  # Left side (compact manager)

        # Track visible docks to manage area visibility
        self._visible_docks = set()

        # Create some actuators
        self._create_actuators()

        # Hide all docks after everything is set up (use timer to ensure it happens after widget is shown)
        QtCore.QTimer.singleShot(100, self._hide_all_docks)

        # Status bar
        self.statusBar().showMessage("Ready. Try clicking the Init and Show Widget buttons!")

    def _create_actuators(self):
        """Create test actuators"""
        self.actuators = []

        actuator_configs = [
            ('X_Axis', 'Mock'),
            ('Y_Axis', 'Mock'),
            ('Z_Axis', 'Mock'),
        ]

        for i, (name, instrument) in enumerate(actuator_configs):
            self.statusBar().showMessage(f"Creating {name}...")
            QtWidgets.QApplication.processEvents()

            # Create widget container
            widget = QtWidgets.QWidget()

            # Create DAQ_Move
            actuator = DAQ_Move(widget, title=name)
            actuator.actuator = instrument

            # Create dock (initially hidden)
            dock = Dock(name, size=(300, 400))
            dock.addWidget(widget)

            # Add dock to area
            if i == 0:
                self.dockarea.addDock(dock, 'left')
            else:
                self.dockarea.addDock(dock, 'bottom', self.actuators[-1].dock)

            # Store dock reference in module (will be hidden later)
            actuator.dock = dock

            self.actuators.append(actuator)

            # Add to compact manager
            compact_widget = self.compact_manager.add_move_widget(actuator)

            # Connect to track dock visibility
            compact_widget.get_action('pop_out').triggered.connect(
                lambda checked=False, d=dock: self._update_dockarea_visibility()
            )

            QtWidgets.QApplication.processEvents()

        self.statusBar().showMessage(f"Created {len(self.actuators)} actuators. Click Init to initialize them!")

    def _hide_all_docks(self):
        """Hide all docks after initialization"""
        for actuator in self.actuators:
            if actuator.dock:
                actuator.dock.hide()

        # Sync button states
        for widget in self.compact_manager.move_widgets:
            widget._sync_pop_out_state()

    def _on_add_move_requested(self, name: str, actuator_type: str):
        """Handle request to add a new actuator"""
        self.statusBar().showMessage(f"Creating {name} [{actuator_type}]...")
        QtWidgets.QApplication.processEvents()

        try:
            # Create widget container
            widget = QtWidgets.QWidget()

            # Create DAQ_Move
            actuator = DAQ_Move(widget, title=name)
            actuator.actuator = actuator_type

            # Create dock (initially hidden)
            dock = Dock(name, size=(300, 400))
            dock.addWidget(widget)

            # Add dock to area
            if len(self.actuators) == 0:
                self.dockarea.addDock(dock, 'left')
            else:
                self.dockarea.addDock(dock, 'bottom', self.actuators[-1].dock)

            # Store dock reference in module
            actuator.dock = dock

            # Hide the dock initially
            dock.hide()

            self.actuators.append(actuator)

            # Add to compact manager
            compact_widget = self.compact_manager.add_move_widget(actuator)

            # Connect to track dock visibility
            compact_widget.get_action('pop_out').triggered.connect(
                lambda checked=False, d=dock: self._update_dockarea_visibility()
            )

            # Sync button state to reflect hidden dock
            compact_widget._sync_pop_out_state()

            self.statusBar().showMessage(f"Added {name} [{actuator_type}]")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to add actuator:\n{str(e)}")
            self.statusBar().showMessage(f"Error adding {name}")

    def _update_dockarea_visibility(self):
        """Check if any docks are visible and update area visibility accordingly"""
        QtCore.QTimer.singleShot(100, self._check_dock_visibility)

    def _check_dock_visibility(self):
        """Check actual dock visibility after brief delay"""
        any_visible = False
        for actuator in self.actuators:
            if actuator.dock and actuator.dock.isVisible():
                any_visible = True
                break

        # If no docks visible, we could hide the dockarea parent widget
        # For now, just update status
        if any_visible:
            self.statusBar().showMessage("Dock widget is visible")
        else:
            self.statusBar().showMessage("All dock widgets hidden")


def main():
    """Run the example"""
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')

    window = CompactMoveExample()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
