"""LECO Network Manager GUI — Phase 2.

Provides a single window for monitoring and controlling a LECO network:

- **Network panel**: start/stop coordinator and proxy processes.
- **Components table**: live list of all signed-in LECO components, with
  expandable actor detail rows and [✕] shutdown buttons.

Thread model
------------
Main thread (Qt)
└── LECOManagerGUI  (CustomApp)
    │  Owns LECONetworkMonitor and LECOMonitorAdapter.
    └── LECONetworkMonitor._poll_thread  (daemon Python thread)
        Calls refresh_components / refresh_actor_details.
        Results are emitted as Qt signals via LECOMonitorAdapter
        so they arrive safely in the main thread.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from qtpy import QtWidgets, QtCore, QtGui
from qtpy.QtCore import QObject, Signal, Slot
from qtpy.QtGui import QColor

from pymodaq_gui.utils.custom_app import CustomApp
from pymodaq_gui.utils.dock import Dock
from pymodaq_gui.utils.widgets.qled import QLED
from pyleco.core import COORDINATOR_PORT

from pymodaq.utils.leco.leco_manager import (
    ComponentRecord,
    CoordinatorRecord,
    LECONetworkMonitor,
    ProxyRecord,
)

logger = logging.getLogger(__name__)


# ── Qt adapter (callback → signal) ────────────────────────────────────────────

class LECOMonitorAdapter(QObject):
    """Wraps ``LECONetworkMonitor`` plain callbacks as Qt signals.

    The monitor's background thread calls the plain-callable callbacks; this
    adapter re-emits them as Qt signals so updates arrive in the GUI (main)
    thread safely via Qt's queued-connection mechanism.
    """

    components_changed = Signal(list)            # list[ComponentRecord]
    actor_details_changed = Signal(object)       # ComponentRecord
    proxy_status_changed = Signal(object)        # ProxyRecord
    coordinator_status_changed = Signal(object)  # CoordinatorRecord
    nodes_changed = Signal(dict)                 # dict[str, str]

    def __init__(self, monitor: LECONetworkMonitor, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.monitor = monitor
        monitor.on_components_changed = self.components_changed.emit
        monitor.on_actor_details_changed = self.actor_details_changed.emit
        monitor.on_proxy_status_changed = self.proxy_status_changed.emit
        monitor.on_coordinator_status_changed = self.coordinator_status_changed.emit
        monitor.on_nodes_changed = self.nodes_changed.emit


# ── AddProxyDialog ─────────────────────────────────────────────────────────────

class AddProxyDialog(QtWidgets.QDialog):
    """Simple dialog to collect in_port, out_port, and label for a new proxy."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Proxy')

        form = QtWidgets.QFormLayout()
        self._in_port = QtWidgets.QSpinBox()
        self._in_port.setRange(1024, 65535)
        self._in_port.setValue(11100)
        self._out_port = QtWidgets.QSpinBox()
        self._out_port.setRange(1024, 65535)
        self._out_port.setValue(11099)
        self._label = QtWidgets.QLineEdit()
        form.addRow('Publisher port (in):', self._in_port)
        form.addRow('Subscriber port (out):', self._out_port)
        form.addRow('Label:', self._label)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    @property
    def in_port(self) -> int:
        return self._in_port.value()

    @property
    def out_port(self) -> int:
        return self._out_port.value()

    @property
    def label(self) -> str:
        return self._label.text().strip()


# ── ConnectDialog ──────────────────────────────────────────────────────────────

class ConnectDialog(QtWidgets.QDialog):
    """Collect coordinator host/port before connecting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Connect to Coordinator')

        form = QtWidgets.QFormLayout()
        self._host = QtWidgets.QLineEdit('localhost')
        self._port = QtWidgets.QSpinBox()
        self._port.setRange(1024, 65535)
        self._port.setValue(COORDINATOR_PORT)
        form.addRow('Host:', self._host)
        form.addRow('Port:', self._port)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    @property
    def host(self) -> str:
        return self._host.text().strip()

    @property
    def port(self) -> int:
        return self._port.value()


# ── LogPanel ───────────────────────────────────────────────────────────────────

class LogPanel(QtWidgets.QWidget):
    """Tails a text log file and displays new lines in a QPlainTextEdit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_path: Optional[Path] = None
        self._pos: int = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)

        self._combo = QtWidgets.QComboBox()
        self._text = QtWidgets.QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(2000)
        font = QtGui.QFont('Monospace')
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        self._text.setFont(font)

        clear_btn = QtWidgets.QPushButton('Clear')
        clear_btn.clicked.connect(self._text.clear)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel('Source:'))
        top.addWidget(self._combo, stretch=1)
        top.addWidget(clear_btn)
        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self._text)
        self.setLayout(layout)

    def start_tailing(self, log_path: Path, label: str = 'coordinator'):
        """Start tailing *log_path*, adding it to the source combo if not present."""
        self._log_path = log_path
        self._pos = 0
        if self._combo.findText(label) == -1:
            self._combo.addItem(label, userData=log_path)
        self._timer.start()

    def stop_tailing(self):
        """Stop the tail timer."""
        self._timer.stop()

    def _poll(self):
        if self._log_path is None or not self._log_path.exists():
            return
        try:
            with open(self._log_path) as f:
                f.seek(self._pos)
                new = f.read()
                self._pos = f.tell()
            if new:
                self._text.appendPlainText(new.rstrip())
        except OSError:
            pass


# ── NetworkPanel ───────────────────────────────────────────────────────────────

class NetworkPanel(QtWidgets.QWidget):
    """Shows connection status LEDs, coordinator row, and proxy rows.

    Signals
    -------
    start_proxy_requested(in_port, out_port, label)
    remove_proxy_requested(in_port)
    start_coordinator_requested(host, port, namespace)
    stop_coordinator_requested()
    """

    start_proxy_requested = Signal(int, int, str)
    remove_proxy_requested = Signal(int)
    start_coordinator_requested = Signal(str, int, str)
    stop_coordinator_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proxy_rows: dict[int, QtWidgets.QWidget] = {}

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        # ── Status LEDs ────────────────────────────────────────────────────────
        led_box = QtWidgets.QGroupBox('Status')
        led_grid = QtWidgets.QGridLayout()

        self._led_connected = QLED(readonly=True)
        self._led_connected.set_as_false()
        self._lbl_connected = QtWidgets.QLabel('Coordinator')

        self._led_actors = QLED(readonly=True)
        self._led_actors.set_as_false()
        self._lbl_actors = QtWidgets.QLabel('Actors: 0')

        self._led_directors = QLED(readonly=True)
        self._led_directors.set_as_false()
        self._lbl_directors = QtWidgets.QLabel('Directors: 0')

        led_grid.addWidget(self._led_connected, 0, 0)
        led_grid.addWidget(self._lbl_connected, 0, 1)
        led_grid.addWidget(self._led_actors, 1, 0)
        led_grid.addWidget(self._lbl_actors, 1, 1)
        led_grid.addWidget(self._led_directors, 2, 0)
        led_grid.addWidget(self._lbl_directors, 2, 1)
        led_grid.setColumnStretch(1, 1)
        led_box.setLayout(led_grid)

        # ── Coordinator row ────────────────────────────────────────────────────
        coord_box = QtWidgets.QGroupBox('Coordinator')
        coord_h = QtWidgets.QHBoxLayout()
        self._coord_info = QtWidgets.QLabel('not connected')
        self._coord_start_btn = QtWidgets.QPushButton('Start…')
        self._coord_stop_btn = QtWidgets.QPushButton('Stop')
        self._coord_stop_btn.setEnabled(False)
        coord_h.addWidget(self._coord_info, stretch=1)
        coord_h.addWidget(self._coord_start_btn)
        coord_h.addWidget(self._coord_stop_btn)
        coord_box.setLayout(coord_h)

        self._coord_start_btn.clicked.connect(self._on_start_coordinator)
        self._coord_stop_btn.clicked.connect(self.stop_coordinator_requested)

        # ── Proxy area ─────────────────────────────────────────────────────────
        proxy_box = QtWidgets.QGroupBox('Proxies')
        self._proxy_layout = QtWidgets.QVBoxLayout()
        self._add_proxy_btn = QtWidgets.QPushButton('+ Add proxy…')
        self._add_proxy_btn.clicked.connect(self._on_add_proxy)
        self._proxy_layout.addWidget(self._add_proxy_btn)
        proxy_box.setLayout(self._proxy_layout)

        # ── Linked Nodes ───────────────────────────────────────────────────────
        nodes_box = QtWidgets.QGroupBox('Linked Nodes')
        nodes_vbox = QtWidgets.QVBoxLayout()
        self._nodes_list = QtWidgets.QListWidget()
        nodes_vbox.addWidget(self._nodes_list)
        nodes_box.setLayout(nodes_vbox)

        layout.addWidget(led_box)
        layout.addWidget(coord_box)
        layout.addWidget(proxy_box)
        layout.addWidget(nodes_box)
        layout.addStretch()
        self.setLayout(layout)

    # ── Status LED updates ─────────────────────────────────────────────────────

    @Slot(object)
    def update_coordinator(self, record: CoordinatorRecord):
        self._led_connected.set_as(record.alive)
        ns = record.namespace or record.host
        state = 'connected' if record.alive else 'disconnected'
        self._coord_info.setText(f'{ns} @ {record.host}:{record.port}  [{state}]')
        self._coord_stop_btn.setEnabled(record.alive and record.process is not None)

    @Slot(list)
    def update_component_counts(self, records: list):
        """Update actor/director count LEDs from the current component list."""
        n_actors = sum(1 for r in records if r.role == 'actor' and r.reachable)
        n_directors = sum(1 for r in records if r.role == 'director' and r.reachable)
        self._lbl_actors.setText(f'Actors: {n_actors}')
        self._lbl_directors.setText(f'Directors: {n_directors}')
        self._led_actors.set_as(n_actors > 0)
        self._led_directors.set_as(n_directors > 0)

    @Slot(dict)
    def update_nodes(self, nodes: dict):
        """Refresh the Linked Nodes list."""
        self._nodes_list.clear()
        for ns, addr in nodes.items():
            self._nodes_list.addItem(f'{ns}  @  {addr}')

    def _on_start_coordinator(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Start Coordinator')
        form = QtWidgets.QFormLayout()
        host_w = QtWidgets.QLineEdit('localhost')
        port_w = QtWidgets.QSpinBox()
        port_w.setRange(1024, 65535)
        port_w.setValue(COORDINATOR_PORT)
        ns_w = QtWidgets.QLineEdit()
        form.addRow('Host:', host_w)
        form.addRow('Port:', port_w)
        form.addRow('Namespace:', ns_w)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        v = QtWidgets.QVBoxLayout()
        v.addLayout(form)
        v.addWidget(buttons)
        dlg.setLayout(v)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.start_coordinator_requested.emit(
                host_w.text().strip(), port_w.value(), ns_w.text().strip()
            )

    # ── Proxies ────────────────────────────────────────────────────────────────

    @Slot(object)
    def update_proxy(self, record: ProxyRecord):
        if record.in_port not in self._proxy_rows:
            self._add_proxy_row(record)
        else:
            self._refresh_proxy_row(record)

    def _add_proxy_row(self, record: ProxyRecord):
        row = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        led = QLED(readonly=True)
        led.set_as(record.alive)
        led.setFixedWidth(16)
        info = QtWidgets.QLabel(
            f'in:{record.in_port}  out:{record.out_port}'
            + (f'  {record.label}' if record.label else '')
        )
        remove_btn = QtWidgets.QPushButton('✕')
        remove_btn.setFixedWidth(28)
        in_port = record.in_port
        remove_btn.clicked.connect(lambda: self.remove_proxy_requested.emit(in_port))
        h.addWidget(led)
        h.addWidget(info, stretch=1)
        h.addWidget(remove_btn)
        row.setLayout(h)
        # Insert before the [+ Add proxy...] button (last item)
        self._proxy_layout.insertWidget(self._proxy_layout.count() - 1, row)
        self._proxy_rows[record.in_port] = row

    def _refresh_proxy_row(self, record: ProxyRecord):
        row = self._proxy_rows[record.in_port]
        led = row.layout().itemAt(0).widget()
        led.set_as(record.alive)
        # If removed (alive=False and no process), clean up the row
        if not record.alive and record.process is None:
            self._proxy_layout.removeWidget(row)
            row.deleteLater()
            del self._proxy_rows[record.in_port]

    def _on_add_proxy(self):
        dlg = AddProxyDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.start_proxy_requested.emit(dlg.in_port, dlg.out_port, dlg.label)


# ── ComponentsTable ────────────────────────────────────────────────────────────

#: HSV hue angles for each role (0–359).
_ROLE_HUES = {
    'actor':       120,   # green
    'director':    220,   # blue
    'coordinator':  60,   # yellow
    'unknown':       0,   # red  (stale / unreachable)
}


def _role_color(role: str) -> QColor:
    """Return a role badge colour adapted to the current Qt palette.

    In **light** mode the result is a soft pastel (high value, low saturation).
    In **dark** mode the result is a dark, lightly saturated tint so that the
    text — which the palette renders in a light foreground — remains readable.
    """
    from qtpy.QtGui import QPalette
    from qtpy.QtWidgets import QApplication
    palette = QApplication.palette()
    # QPalette.Base lives under ColorRole in PyQt6/PySide6, directly on the
    # class in PyQt5 — handle both.
    base_role = getattr(QPalette, 'ColorRole', QPalette).Base
    base = palette.color(base_role)
    hue = _ROLE_HUES.get(role, 0)
    if base.lightness() < 128:
        # Dark theme — muted tint, low value
        return QColor.fromHsv(hue, 80, 80)
    else:
        # Light theme — pastel, high value
        return QColor.fromHsv(hue, 60, 220)

_COL_NAME   = 0
_COL_ROLE   = 1
_COL_HOST   = 2
_COL_STATUS = 3
_COL_ACTION = 4


class ComponentsTable(QtWidgets.QWidget):
    """Tree widget showing all live LECO components.

    Actors have expandable child rows showing capabilities.
    Each row has a [✕] button to shut down / remove the component.

    Signals
    -------
    shutdown_requested(name)
    """

    shutdown_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setColumnCount(5)
        self._tree.setHeaderLabels(['Name', 'Role', 'Host', 'Status', ''])
        self._tree.header().setStretchLastSection(False)
        hdr = self._tree.header()
        hdr.setSectionResizeMode(_COL_NAME,   QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ROLE,   QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_HOST,   QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_STATUS, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ACTION, QtWidgets.QHeaderView.Fixed)
        hdr.resizeSection(_COL_ACTION, 30)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)
        self.setLayout(layout)

        # name → QTreeWidgetItem
        self._items: dict[str, QtWidgets.QTreeWidgetItem] = {}

    @Slot(list)
    def update_components(self, records: list):
        """Rebuild the tree from a fresh component list."""
        current_names = {r.name for r in records}

        # Remove items no longer in the records list
        for name in list(self._items.keys()):
            if name not in current_names:
                idx = self._tree.indexOfTopLevelItem(self._items[name])
                if idx >= 0:
                    self._tree.takeTopLevelItem(idx)
                del self._items[name]

        for rec in records:
            if rec.name not in self._items:
                self._add_item(rec)
            else:
                self._update_item(rec)

    @Slot(object)
    def update_actor_details(self, record):
        """Update an actor row with refreshed capabilities / status."""
        item = self._items.get(record.name)
        if item is None:
            return
        self._update_item(record)
        # Rebuild capability child rows
        item.takeChildren()
        if record.capabilities:
            self._add_capability_children(item, record)

    def _add_item(self, rec: ComponentRecord):
        item = QtWidgets.QTreeWidgetItem([
            rec.name, rec.role, rec.host or '', self._status_text(rec), '',
        ])
        color = _role_color(rec.role)
        for col in range(self._tree.columnCount()):
            item.setBackground(col, color)
        self._tree.addTopLevelItem(item)
        self._items[rec.name] = item

        # Shutdown/remove button in last column
        btn = QtWidgets.QPushButton('✕')
        btn.setFixedSize(24, 24)
        name = rec.name
        btn.clicked.connect(lambda: self.shutdown_requested.emit(name))
        self._tree.setItemWidget(item, _COL_ACTION, btn)

    def _update_item(self, rec: ComponentRecord):
        item = self._items.get(rec.name)
        if item is None:
            return
        item.setText(_COL_HOST, rec.host or '')
        item.setText(_COL_STATUS, self._status_text(rec))
        # Dim stale rows
        color = _role_color(rec.role)
        if not rec.reachable:
            color = _role_color('unknown')
        for col in range(self._tree.columnCount()):
            item.setBackground(col, color)

    def _add_capability_children(self, item: QtWidgets.QTreeWidgetItem, rec: ComponentRecord):
        caps = rec.capabilities or {}
        for obs in caps.get('observables', []):
            name = obs.get('name', '?')
            shape = obs.get('shape', '')
            child = QtWidgets.QTreeWidgetItem(
                ['', f'Observable: {name}', f'shape={shape}', '', '']
            )
            item.addChild(child)
        for var in caps.get('variables', []):
            name = var.get('name', '?')
            kind = var.get('kind', 'variable')
            lo = var.get('lo', '')
            hi = var.get('hi', '')
            detail = f'lo={lo}  hi={hi}' if lo != '' and hi != '' else ''
            child = QtWidgets.QTreeWidgetItem(
                ['', f'{kind}: {name}', detail, '', '']
            )
            item.addChild(child)
        item.setExpanded(True)

    @staticmethod
    def _status_text(rec: ComponentRecord) -> str:
        if not rec.reachable:
            return 'no reply'
        if rec.grabbed_names:
            return 'grabbing'
        return 'idle'


# ── LECOManagerGUI ─────────────────────────────────────────────────────────────

class LECOManagerGUI(CustomApp):
    """LECO Network Manager — main application window.

    Layout
    ------
    Toolbar: [Connect] [Disconnect] [Refresh now]
    Left dock: NetworkPanel (status LEDs + coordinator + proxies)
    Right dock: ComponentsTable (live component tree)
    """

    params = [
        {'title': 'Host:', 'name': 'host', 'type': 'str', 'value': 'localhost'},
        {'title': 'Port:', 'name': 'port', 'type': 'int', 'value': COORDINATOR_PORT},
        {'title': 'Fast poll interval (s):', 'name': 'fast_interval',
         'type': 'float', 'value': 2.0, 'min': 0.5},
        {'title': 'Slow poll interval (s):', 'name': 'slow_interval',
         'type': 'float', 'value': 5.0, 'min': 1.0},
    ]

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent, title='LECO Network Manager', **kwargs)

        self._monitor = LECONetworkMonitor()
        self._adapter = LECOMonitorAdapter(self._monitor, parent=self)

        self._network_panel: Optional[NetworkPanel] = None
        self._components_table: Optional[ComponentsTable] = None
        self._connected = False

        self.setup_ui()
        self._wire_signals()

    # ── CustomApp hooks ────────────────────────────────────────────────────────

    def setup_docks(self):
        self._network_panel = NetworkPanel()
        dock_net = Dock('Network', size=(300, 500))
        dock_net.addWidget(self._network_panel)

        self._components_table = ComponentsTable()
        dock_comp = Dock('Components', size=(600, 500))
        dock_comp.addWidget(self._components_table)

        self._log_panel = LogPanel()
        dock_log = Dock('Logs', size=(400, 500))
        dock_log.addWidget(self._log_panel)

        self.dockarea.addDock(dock_net, 'left')
        self.dockarea.addDock(dock_comp, 'right', dock_net)
        self.dockarea.addDock(dock_log, 'right', dock_comp)

    def setup_actions(self):
        self.add_action('connect', 'Connect', icon_name='network_on',
                        tip='Connect to LECO coordinator and start polling')
        self.add_action('disconnect', 'Disconnect', icon_name='network_off',
                        tip='Stop polling and release the coordinator connection')
        self.add_action('refresh', 'Refresh now', icon_name='refresh2',
                        tip='Force immediate component refresh')
        self.get_action('disconnect').setEnabled(False)
        self.get_action('refresh').setEnabled(False)

    def connect_things(self):
        self.get_action('connect').triggered.connect(self._on_connect)
        self.get_action('disconnect').triggered.connect(self._on_disconnect)
        self.get_action('refresh').triggered.connect(self._on_refresh)

    # ── Signal wiring ──────────────────────────────────────────────────────────

    def _wire_signals(self):
        # Monitor → GUI
        self._adapter.components_changed.connect(self._components_table.update_components)
        self._adapter.components_changed.connect(self._network_panel.update_component_counts)
        self._adapter.actor_details_changed.connect(self._components_table.update_actor_details)
        self._adapter.coordinator_status_changed.connect(self._network_panel.update_coordinator)
        self._adapter.coordinator_status_changed.connect(self._on_coordinator_log_update)
        self._adapter.proxy_status_changed.connect(self._network_panel.update_proxy)
        self._adapter.nodes_changed.connect(self._network_panel.update_nodes)

        # NetworkPanel → monitor actions
        self._network_panel.start_coordinator_requested.connect(self._on_start_coordinator)
        self._network_panel.stop_coordinator_requested.connect(self._on_stop_coordinator)
        self._network_panel.start_proxy_requested.connect(self._on_add_proxy)
        self._network_panel.remove_proxy_requested.connect(self._on_remove_proxy)

        # ComponentsTable → monitor actions
        self._components_table.shutdown_requested.connect(self._on_shutdown_component)

    @Slot(object)
    def _on_coordinator_log_update(self, record: CoordinatorRecord):
        """Start or stop tailing the coordinator log based on alive state."""
        if record.log_path and record.alive:
            self._log_panel.start_tailing(record.log_path)
        elif not record.alive:
            self._log_panel.stop_tailing()

    def _widget_parent(self) -> Optional[QtWidgets.QWidget]:
        """Return a valid QWidget parent for dialogs (mainwindow or None)."""
        mw = getattr(self, 'mainwindow', None)
        if isinstance(mw, QtWidgets.QWidget):
            return mw
        return None

    # ── Toolbar actions ────────────────────────────────────────────────────────

    @Slot()
    def _on_connect(self):
        if self._connected:
            return
        dlg = ConnectDialog(self._widget_parent())
        # Pre-fill from settings
        dlg._host.setText(self.settings['host'])
        dlg._port.setValue(self.settings['port'])
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        host, port = dlg.host, dlg.port
        try:
            self._monitor.connect(host=host, port=port)
            self._monitor.start_polling()
            self._connected = True
            self.get_action('connect').setEnabled(False)
            self.get_action('disconnect').setEnabled(True)
            self.get_action('refresh').setEnabled(True)
        except ConnectionError as exc:
            QtWidgets.QMessageBox.warning(
                self._widget_parent(), 'Connection failed', str(exc)
            )

    @Slot()
    def _on_disconnect(self):
        self._monitor.stop_polling()
        self._monitor.disconnect()
        self._connected = False
        self.get_action('connect').setEnabled(True)
        self.get_action('disconnect').setEnabled(False)
        self.get_action('refresh').setEnabled(False)
        # Clear the component table
        self._components_table.update_components([])
        self._network_panel.update_component_counts([])

    @Slot()
    def _on_refresh(self):
        self._monitor.refresh_components()

    # ── Coordinator ────────────────────────────────────────────────────────────

    @Slot(str, int, str)
    def _on_start_coordinator(self, host: str, port: int, namespace: str):
        try:
            self._monitor.start_coordinator(host=host, port=port,
                                            namespace=namespace or None)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self._widget_parent(), 'Start failed', str(exc)
            )

    @Slot()
    def _on_stop_coordinator(self):
        self._monitor.stop_coordinator()

    # ── Proxy ──────────────────────────────────────────────────────────────────

    @Slot(int, int, str)
    def _on_add_proxy(self, in_port: int, out_port: int, label: str):
        try:
            self._monitor.add_proxy(in_port, out_port, label)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self._widget_parent(), 'Proxy failed', str(exc)
            )

    @Slot(int)
    def _on_remove_proxy(self, in_port: int):
        self._monitor.remove_proxy(in_port)

    # ── Component shutdown ─────────────────────────────────────────────────────

    @Slot(str)
    def _on_shutdown_component(self, name: str):
        self._monitor.shutdown_component(name)

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Stop polling, send shutdown to all live actors, release ZMQ resources."""
        self._monitor.stop_polling()
        # Gracefully shut down all live actors before releasing the director
        if self._connected:
            for rec in list(self._monitor.components):
                if rec.role == 'actor' and rec.reachable:
                    try:
                        self._monitor.shutdown_component(rec.name)
                    except Exception:
                        pass
            self._monitor.disconnect()
        self._monitor.stop_coordinator()
        super().closeEvent(event)


# ── Entry point ────────────────────────────────────────────────────────────────

def create_manager_gui():
    """Create a standalone LECO Network Manager wrapped in a QMainWindow.

    Must be called after a QApplication exists.  Creates a :class:`DockArea`,
    sets it as the central widget of a fresh :class:`QMainWindow` (so that
    ``CustomApp`` correctly resolves ``self.dockarea`` and ``self.mainwindow``),
    then constructs :class:`LECOManagerGUI`.

    Returns
    -------
    win : QMainWindow
        The top-level window — call ``win.show()`` to display.
    gui : LECOManagerGUI
        The manager GUI instance.
    """
    from pymodaq_gui.utils.dock import DockArea
    from qtpy.QtWidgets import QMainWindow

    area = DockArea()
    win = QMainWindow()
    win.setCentralWidget(area)   # area.parent() = win → CustomApp picks it up
    gui = LECOManagerGUI(area)
    return win, gui


def main():  # pragma: no cover
    """CLI entry point: ``leco-manager``."""
    import sys
    from pymodaq_gui.qt_utils import mkQApp
    app = mkQApp('LECO Network Manager')
    win, _ = create_manager_gui()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':  # pragma: no cover
    main()
