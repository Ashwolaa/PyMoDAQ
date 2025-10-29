"""
Compact widget for DAQ_Move modules.

Provides a toolbar-style compact representation of a DAQ_Move module.
"""

from typing import TYPE_CHECKING
from qtpy import QtWidgets, QtCore
from qtpy.QtCore import Signal

from pymodaq_gui.managers.action_manager import ActionManager
from pymodaq_gui.utils import QLED
import qtawesome as qta
if TYPE_CHECKING:
    from pymodaq.control_modules.daq_move import DAQ_Move


class CompactMoveWidget(QtWidgets.QWidget, ActionManager):
    """A compact toolbar representation of a DAQ_Move module.

    Parameters
    ----------
    module : DAQ_Move
        The DAQ_Move instance to represent
    """

    close_requested = Signal()

    def __init__(self, module: 'DAQ_Move', parent=None):
        QtWidgets.QWidget.__init__(self, parent)

        self.module = module

        # Create toolbar
        self.set_toolbar(QtWidgets.QToolBar())
        self.toolbar.setIconSize(QtCore.QSize(20, 20))

        ActionManager.__init__(self, toolbar=self.toolbar)

        # Setup UI
        self._setup_ui()
        self._setup_actions()
        self._connect_signals()

    def _setup_ui(self):
        """Setup the widget UI"""
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        self.setLayout(layout)

        # Set maximum height to keep it compact
        self.setMaximumHeight(40)

    def _setup_actions(self):
        """Setup toolbar actions"""
        import qtawesome as qta

        # Left side: Init status & control
        # State LED (shows at a glance if module is initialized)
        self.state_led = QLED()
        self.state_led.set_as(False)
        self.state_led.setToolTip("Initialization state: Green = Initialized, Red = Not initialized")
        self.add_widget('state', self.state_led, auto_toolbar=True)

        # Init/Deinit button (next to its LED)
        self.add_action('init', 'Init', icon_name=qta.icon('mdi.connection', color='white'),
                       tip='Initialize/De-initialize module', checkable=True, checked=False)
        self.toolbar.addSeparator()

        # Settings button
        self.add_action('settings', 'Settings', icon_name=qta.icon('mdi6.file-tree', color='white'),
                       tip='Show/hide settings')
        
        self.toolbar.addSeparator()

        # Module identification
        # Module name label
        name_label = QtWidgets.QLabel(f"<b>{self.module.title}</b>")
        name_label.setMinimumWidth(80)
        self.add_widget('name_label', name_label, auto_toolbar=True)

        # Instrument type label
        instrument_name = self.module.actuator if hasattr(self.module, 'actuator') and self.module.actuator else 'Not Set'
        type_label = QtWidgets.QLabel(f"<i>{instrument_name}</i>")
        type_label.setStyleSheet("color: gray;")
        type_label.setMinimumWidth(60)
        self.add_widget('type_label', type_label, auto_toolbar=True)

        self.toolbar.addSeparator()

        # Move status & position
        # Move done LED (shows if actuator reached target position)
        self.move_done_led = QLED()
        self.move_done_led.set_as(False)
        self.move_done_led.setToolTip("Move status: Green = Position reached, Red = Moving or idle")
        self.add_widget('move_done', self.move_done_led, auto_toolbar=True)



        self.toolbar.addSeparator()

        # View & control buttons
        # Show position toggle button
        self.add_action('show_position', 'Show Pos', icon_name=qta.icon('mdi.crosshairs-gps', color='white'),
                       tip='Show/hide current position', checkable=True, checked=False)

        # Current position label (initially hidden)
        self.position_label = QtWidgets.QLabel("")
        self.position_label.setStyleSheet("color: #4CAF50; font-weight: bold;")  # Green color
        # self.position_label.setMinimumWidth(80)
        self.position_label.setFixedWidth(80)
        self.position_label.setVisible(False)
        self.add_widget('position', self.position_label, auto_toolbar=True, visible=False)

        self.toolbar.addSeparator()


        # Add spacer to push close button to the right
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        self.toolbar.addSeparator()

        # Pop-out button (checkable to show state)
        self.add_action('pop_out', 'Show Widget', icon_name=qta.icon('mdi6.application-export', color='white'),
                       tip='Show/hide full module widget', checkable=True, checked=False)
        self.toolbar.addSeparator()

        # Right side: Close button
        self.add_action('close', '', icon_name=qta.icon('mdi.close-circle', color='#F44336'),  # Red color
                       tip='Close and remove this module')

    def _connect_signals(self):
        """Connect toolbar actions to module methods"""
        # Close button
        self.connect_action('close', self._on_close)

        # Init button
        self.connect_action('init', self._on_init)

        # Show position button
        self.connect_action('show_position', self._on_show_position_toggled)

        # Settings button
        self.connect_action('settings', self._on_settings)

        # Pop out button
        self.connect_action('pop_out', self._on_pop_out)

        # Connect to module's init signal
        if hasattr(self.module, 'init_signal'):
            self.module.init_signal.connect(self._update_init_state)

        # Connect to module's move done signal
        if hasattr(self.module, 'move_done_signal'):
            self.module.move_done_signal.connect(self._update_move_done)

        # Connect to module's current value signal
        if hasattr(self.module, 'current_value_signal'):
            self.module.current_value_signal.connect(self._update_position)

        # Update initial state
        if hasattr(self.module, 'initialized_state'):
            self._update_init_state(self.module.initialized_state)

        # Sync pop-out button with dock visibility
        self._sync_pop_out_state()

    def _update_init_state(self, initialized: bool):
        """Update UI based on initialization state"""
        self.state_led.set_as(initialized)
        self.get_action('init').setChecked(initialized)

    def _update_move_done(self, data_actuator):
        """Update move done LED when position is reached"""
        # Set LED to green when move is done
        self.move_done_led.set_as(True)
        # Could use a timer to reset it after a short time if desired

    def _update_position(self, data_actuator):
        """Update position display when current value changes"""
        try:
            # Format the position value
            value = data_actuator.value()
            units = data_actuator.units
            self.position_label.setText(f"{value:.3f} {units}")

            # Reset move done LED when position changes (indicating movement)
            # We'll set it back to green when move_done_signal fires
            self.move_done_led.set_as(False)
        except Exception as e:
            print(f"Error updating position: {e}")

    def _on_show_position_toggled(self, checked: bool):
        """Toggle position display visibility"""
        self.position_label.setVisible(checked)

    def _sync_pop_out_state(self):
        """Sync the pop-out button state with actual dock visibility"""
        if hasattr(self.module, 'dock') and self.module.dock:
            is_visible = self.module.dock.isVisible()
            self.get_action('pop_out').setChecked(is_visible)
            if is_visible:
                self.get_action('pop_out').setText('Hide Widget')
            else:
                self.get_action('pop_out').setText('Show Widget')

    def _on_close(self):
        """Handle close button"""
        reply = QtWidgets.QMessageBox.question(
            self, 'Confirm Close',
            f'Close module "{self.module.title}"?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            # Hide the dock first
            if hasattr(self.module, 'dock') and self.module.dock:
                self.module.dock.setVisible(False)

            # Quit the module
            self.module.quit_fun()

            # Emit signal
            self.close_requested.emit()

    def _on_init(self, checked: bool):
        """Handle init/deinit button"""
        if checked:
            # Initialize
            self.module.init_hardware_ui()
        else:
            # Deinitialize
            self.module.init_hardware_ui(False)

    def _on_settings(self):
        """Handle settings button - toggle settings visibility"""
        if hasattr(self.module.ui, '_tree') and self.module.ui._tree:
            # Toggle the settings tree visibility
            current = self.module.ui._tree.isVisible()
            self.module.ui._tree.setVisible(not current)

    def _on_pop_out(self):
        """Handle pop out button - show/hide the full widget"""
        try:
            if not (hasattr(self.module, 'dock') and self.module.dock):
                return

            dock = self.module.dock
            current = dock.isVisible()

            # Simple approach: just toggle dock visibility
            if current:
                dock.hide()
            else:
                dock.show()
            # Update button state and text
            new_state = not current
            self.get_action('pop_out').setChecked(new_state)

            if new_state:
                self.get_action('pop_out').setText('Hide Widget')
            else:
                self.get_action('pop_out').setText('Show Widget')

        except Exception as e:
            print(f"Error in _on_pop_out: {e}")
            import traceback
            traceback.print_exc()


class CompactMoveManager(QtWidgets.QWidget, ActionManager):
    """Widget to manage multiple compact move widgets"""

    add_move_requested = Signal(str, str)  # (name, actuator_type)

    def __init__(self, parent=None, dockarea=None):
        QtWidgets.QWidget.__init__(self, parent)

        self.dockarea = dockarea  # Store reference to dockarea

        # Create toolbar for add button
        self.add_toolbar = QtWidgets.QToolBar()
        self.add_toolbar.setIconSize(QtCore.QSize(20, 20))

        ActionManager.__init__(self, toolbar=self.add_toolbar)

        self.move_widgets:list[CompactMoveWidget] = []  # List of CompactMoveWidget instances

        self._setup_ui()

    def _setup_ui(self):
        """Setup the manager widget UI"""
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Title
        title_label = QtWidgets.QLabel("<h3>Actuators</h3>")
        main_layout.addWidget(title_label)

        # Add button with nice icon for dark mode
        import qtawesome as qta
        self._setup_actions()
        self._connect_signals()


        main_layout.addWidget(self.add_toolbar)

        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        main_layout.addWidget(line)

        # Scrollable area for move widgets
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.moves_container = QtWidgets.QWidget()
        self.moves_layout = QtWidgets.QVBoxLayout()
        self.moves_layout.setSpacing(2)
        self.moves_layout.addStretch()  # Add stretch to push widgets to top
        self.moves_container.setLayout(self.moves_layout)

        scroll_area.setWidget(self.moves_container)
        main_layout.addWidget(scroll_area)

        self.setLayout(main_layout)

    def _setup_actions(self):
        """Setup toolbar actions"""
        # Init All - State LED and button
        self.state_led = QLED()
        self.state_led.set_as(False)
        self.state_led.setToolTip("Initialization state: Green = All initialized, Red = Not all initialized")
        self.add_widget('state', self.state_led, auto_toolbar=True)

        self.add_action('init_all', 'Init All', icon_name=qta.icon('mdi.connection', color='white'),
                       tip='Initialize/De-initialize all actuators', checkable=True, checked=False)

        self.toolbar.addSeparator()

        # Show/Hide All Widgets
        self.add_action('toggle_visibility', 'Show All',
                       icon_name=qta.icon('mdi.eye', color='white'),
                       tip='Show/hide all actuator widgets', checkable=True, checked=False)

        self.toolbar.addSeparator()

        # Stop All
        self.add_action('stop_all', 'Stop All',
                       icon_name=qta.icon('mdi.stop-circle', color='#FF9800'),  # Orange color
                       tip='Emergency stop for all actuators')

        self.toolbar.addSeparator()

        # Enable/Disable All Controls
        self.add_action('enable_all', 'Disable All',
                       icon_name=qta.icon('mdi.lock-open', color='white'),
                       tip='Enable/disable all actuator controls', checkable=True, checked=True)

        self.toolbar.addSeparator()

        # Refresh Status
        self.add_action('refresh', 'Refresh',
                       icon_name=qta.icon('mdi.refresh', color='white'),
                       tip='Refresh all status indicators')
        self.toolbar.addSeparator()       

        # Add spacer to push close button to the right
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        # self.toolbar.addSeparator()
        # Add actuator

        self.add_action('add_move', 'Add Actuator',
                       icon_name=qta.icon('mdi.plus-circle', color='#4CAF50'),  # Green color
                       tip='Add a new actuator module')


    def _connect_signals(self):
        self.connect_action('add_move', self._on_add_move_clicked)
        self.connect_action('init_all', self._on_init_all)
        self.connect_action('toggle_visibility', self._on_toggle_visibility)
        self.connect_action('stop_all', self._on_stop_all)
        self.connect_action('enable_all', self._on_enable_all)
        self.connect_action('refresh', self._on_refresh)



    def _on_add_move_clicked(self):
        """Handle add move button click - show dialog to add new actuator"""
        from pymodaq.control_modules.daq_move import ACTUATOR_TYPES

        # Create dialog
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Add Actuator")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QFormLayout()

        # Name input
        name_edit = QtWidgets.QLineEdit()
        name_edit.setPlaceholderText("Enter actuator name...")
        layout.addRow("Name:", name_edit)

        # Type selection
        type_combo = QtWidgets.QComboBox()
        type_combo.addItems(ACTUATOR_TYPES)
        layout.addRow("Type:", type_combo)

        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addRow(button_box)

        dialog.setLayout(layout)

        # Show dialog
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            name = name_edit.text().strip()
            if not name:
                QtWidgets.QMessageBox.warning(self, "Invalid Name", "Please enter a valid name")
                return

            actuator_type = type_combo.currentText()
            self.add_move_requested.emit(name, actuator_type)

    def add_move_widget(self, module: 'DAQ_Move'):
        """Add a move widget to the manager

        Parameters
        ----------
        module : DAQ_Move
            The DAQ_Move instance
        """
        move_widget = CompactMoveWidget(module)

        # Connect close signal
        move_widget.close_requested.connect(
            lambda: self._on_move_close_requested(move_widget)
        )

        # Connect to module's init signal to update global state
        if hasattr(module, 'init_signal'):
            module.init_signal.connect(lambda state: self._update_global_init_state())

        self.move_widgets.append(move_widget)
        # Insert before the stretch item (which is the last item)
        self.moves_layout.insertWidget(self.moves_layout.count() - 1, move_widget)

        # Update global init state
        self._update_global_init_state()

        return move_widget

    def remove_move_widget(self, move_widget: CompactMoveWidget):
        """Remove a move widget from the manager"""
        if move_widget in self.move_widgets:
            self.move_widgets.remove(move_widget)
            self.moves_layout.removeWidget(move_widget)
            move_widget.deleteLater()

            # Update global init state after removal
            self._update_global_init_state()

    def _on_move_close_requested(self, move_widget: CompactMoveWidget):
        """Handle move close request"""
        self.remove_move_widget(move_widget)

    def clear_moves(self):
        """Remove all move widgets"""
        for move_widget in self.move_widgets[:]:
            self.remove_move_widget(move_widget)

    def _on_init_all(self, checked: bool):
        """Initialize or deinitialize all actuators"""
        for move_widget in self.move_widgets:
            # Trigger the init action on each widget
            move_widget._on_init(checked)

        # Update the state LED based on all modules
        self._update_global_init_state()

    def _on_toggle_visibility(self, checked: bool):
        """Show or hide all actuator docks"""
        for move_widget in self.move_widgets:
            if hasattr(move_widget.module, 'dock') and move_widget.module.dock:
                move_widget.module.dock.setVisible(checked)
                # Update the individual pop-out button state
                move_widget._sync_pop_out_state()

        # Update button text
        if checked:
            self.get_action('toggle_visibility').setText('Hide All')
            self.get_action('toggle_visibility').setIcon(qta.icon('mdi.eye-off', color='white'))
        else:
            self.get_action('toggle_visibility').setText('Show All')
            self.get_action('toggle_visibility').setIcon(qta.icon('mdi.eye', color='white'))

    def _on_stop_all(self):
        """Emergency stop for all actuators"""
        for move_widget in self.move_widgets:
            try:
                # Check if module has a stop method
                if hasattr(move_widget.module, 'stop_Motion'):
                    move_widget.module.stop_Motion()
                elif hasattr(move_widget.module, 'stop'):
                    move_widget.module.stop()
            except Exception as e:
                print(f"Error stopping {move_widget.module.title}: {e}")

    def _on_enable_all(self, checked: bool):
        """Enable or disable all actuator controls"""
        # Enable/disable all move widgets
        for move_widget in self.move_widgets:
            
            for action in move_widget.actions_names:
                if action not in ["state", "move_done"]:
                    move_widget._actions[action].setEnabled(checked)


        # Enable/disable other toolbar actions (but keep LED active for status visibility)
        self.get_action('init_all').setEnabled(checked)
        self.get_action('toggle_visibility').setEnabled(checked)
        self.get_action('stop_all').setEnabled(checked)
        self.get_action('refresh').setEnabled(checked)
        self.get_action('add_move').setEnabled(checked)

        # Update button text and icon
        if checked:
            # Controls are enabled, so button offers to disable them
            self.get_action('enable_all').setText('Disable All')
            self.get_action('enable_all').setIcon(qta.icon('mdi.lock-open', color='white'))
        else:
            # Controls are disabled, so button offers to enable them
            self.get_action('enable_all').setText('Enable All')
            self.get_action('enable_all').setIcon(qta.icon('mdi.lock', color='white'))

    def _on_refresh(self):
        """Refresh all status indicators"""
        for move_widget in self.move_widgets:
            try:
                # Update initialization state
                if hasattr(move_widget.module, 'initialized_state'):
                    move_widget._update_init_state(move_widget.module.initialized_state)

                # Sync pop-out button state
                move_widget._sync_pop_out_state()

                # Request current position update if module is initialized
                if hasattr(move_widget.module, 'current_value') and move_widget.module.initialized_state:
                    current_value = move_widget.module.current_value
                    if current_value is not None:
                        move_widget._update_position(current_value)

            except Exception as e:
                print(f"Error refreshing {move_widget.module.title}: {e}")

        # Update global init state
        self._update_global_init_state()

    def _update_global_init_state(self):
        """Update the global initialization LED based on all modules"""
        if not self.move_widgets:
            self.state_led.set_as(False)
            self.get_action('init_all').setChecked(False)
            return

        # Check if all modules are initialized
        all_initialized = all(
            hasattr(widget.module, 'initialized_state') and widget.module.initialized_state
            for widget in self.move_widgets
        )

        self.state_led.set_as(all_initialized)
        self.get_action('init_all').setChecked(all_initialized)
