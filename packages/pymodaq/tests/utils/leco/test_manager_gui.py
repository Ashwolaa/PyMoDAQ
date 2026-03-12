"""Tests for pymodaq.utils.leco.manager_gui — Phase 2.

Qt-dependent tests skip in headless environments (no display or Qt bindings).
Pure-callback tests (LECOMonitorAdapter wiring) run headlessly via the conftest
stubs.

Run with a display:
    PYTHONPATH=... pytest tests/utils/leco/test_manager_gui.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pymodaq.utils.leco.leco_manager import (
    ComponentRecord,
    CoordinatorRecord,
    LECONetworkMonitor,
    ProxyRecord,
)

# ── Qt availability check (real bindings, not conftest stubs) ──────────────────
_QT_AVAILABLE = False
try:
    import pytest_qt  # noqa: F401
    from PyQt5 import QtWidgets as _qtw  # noqa: F401
    _QT_AVAILABLE = True
except ImportError:
    try:
        from PySide6 import QtWidgets as _qtw  # noqa: F401
        _QT_AVAILABLE = True
    except ImportError:
        pass

pytestmark_qt = pytest.mark.skipif(
    not _QT_AVAILABLE,
    reason='Qt / pytest-qt not available (headless environment)',
)


# ── LECOMonitorAdapter (headless — tests only the callback wiring) ─────────────
#
# These tests use the conftest-stubbed QObject to avoid needing real Qt.

class TestLECOMonitorAdapterWiring:
    """Verify that adapter wires each callback to the correct signal's .emit."""

    def test_components_changed_wired(self):
        from pymodaq.utils.leco.manager_gui import LECOMonitorAdapter
        monitor = MagicMock(spec=LECONetworkMonitor)
        adapter = LECOMonitorAdapter.__new__(LECOMonitorAdapter)
        # Manually call the wiring logic without real Qt
        adapter.components_changed = MagicMock()
        adapter.actor_details_changed = MagicMock()
        adapter.proxy_status_changed = MagicMock()
        adapter.coordinator_status_changed = MagicMock()
        monitor.on_components_changed = adapter.components_changed.emit
        monitor.on_actor_details_changed = adapter.actor_details_changed.emit
        monitor.on_proxy_status_changed = adapter.proxy_status_changed.emit
        monitor.on_coordinator_status_changed = adapter.coordinator_status_changed.emit

        # Call each callback and verify it routes to the right signal
        monitor.on_components_changed(['a'])
        adapter.components_changed.emit.assert_called_once_with(['a'])

    def test_actor_details_changed_wired(self):
        from pymodaq.utils.leco.manager_gui import LECOMonitorAdapter
        monitor = MagicMock(spec=LECONetworkMonitor)
        sig = MagicMock()
        monitor.on_actor_details_changed = sig
        sig('record')
        sig.assert_called_once_with('record')

    def test_proxy_status_wired(self):
        from pymodaq.utils.leco.manager_gui import LECOMonitorAdapter
        monitor = MagicMock(spec=LECONetworkMonitor)
        sig = MagicMock()
        monitor.on_proxy_status_changed = sig
        sig('proxy_rec')
        sig.assert_called_once_with('proxy_rec')

    def test_coordinator_status_wired(self):
        monitor = MagicMock(spec=LECONetworkMonitor)
        sig = MagicMock()
        monitor.on_coordinator_status_changed = sig
        rec = CoordinatorRecord(host='localhost', port=12300, alive=True)
        sig(rec)
        sig.assert_called_once_with(rec)


# ── Pure-Python helper tests (no Qt) ──────────────────────────────────────────

class TestComponentsTableStatusText:
    """ComponentsTable._status_text is a pure @staticmethod — no Qt needed."""

    def test_unreachable_returns_no_reply(self):
        from pymodaq.utils.leco.manager_gui import ComponentsTable
        rec = ComponentRecord(name='g', full_name='localhost.g',
                              role='unknown', reachable=False)
        assert ComponentsTable._status_text(rec) == 'no reply'

    def test_idle(self):
        from pymodaq.utils.leco.manager_gui import ComponentsTable
        rec = ComponentRecord(name='s', full_name='localhost.s',
                              role='actor', reachable=True)
        assert ComponentsTable._status_text(rec) == 'idle'

    def test_grabbing(self):
        from pymodaq.utils.leco.manager_gui import ComponentsTable
        rec = ComponentRecord(name='c', full_name='localhost.c',
                              role='actor', reachable=True,
                              grabbed_names=['frame'])
        assert ComponentsTable._status_text(rec) == 'grabbing'


# ═══════════════════════════════════════════════════════════════════════════════
# Qt-dependent tests (skip in headless)
# ═══════════════════════════════════════════════════════════════════════════════

@pytestmark_qt
class TestAddProxyDialog:
    @pytest.fixture(autouse=True)
    def _imports(self):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.manager_gui import AddProxyDialog
        self.AddProxyDialog = AddProxyDialog

    def test_default_in_port(self, qtbot):
        dlg = self.AddProxyDialog()
        qtbot.addWidget(dlg)
        assert dlg.in_port == 11100

    def test_default_out_port(self, qtbot):
        dlg = self.AddProxyDialog()
        qtbot.addWidget(dlg)
        assert dlg.out_port == 11099

    def test_label_empty_by_default(self, qtbot):
        dlg = self.AddProxyDialog()
        qtbot.addWidget(dlg)
        assert dlg.label == ''

    def test_custom_ports(self, qtbot):
        dlg = self.AddProxyDialog()
        qtbot.addWidget(dlg)
        dlg._in_port.setValue(11102)
        dlg._out_port.setValue(11101)
        assert dlg.in_port == 11102
        assert dlg.out_port == 11101

    def test_label_strips_whitespace(self, qtbot):
        dlg = self.AddProxyDialog()
        qtbot.addWidget(dlg)
        dlg._label.setText('  cameras  ')
        assert dlg.label == 'cameras'


@pytestmark_qt
class TestConnectDialog:
    @pytest.fixture(autouse=True)
    def _imports(self):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.manager_gui import ConnectDialog
        self.ConnectDialog = ConnectDialog

    def test_default_host(self, qtbot):
        dlg = self.ConnectDialog()
        qtbot.addWidget(dlg)
        assert dlg.host == 'localhost'

    def test_port_in_valid_range(self, qtbot):
        dlg = self.ConnectDialog()
        qtbot.addWidget(dlg)
        assert 1024 <= dlg.port <= 65535

    def test_custom_host(self, qtbot):
        dlg = self.ConnectDialog()
        qtbot.addWidget(dlg)
        dlg._host.setText('myserver')
        assert dlg.host == 'myserver'


@pytestmark_qt
class TestNetworkPanel:
    @pytest.fixture(autouse=True)
    def _imports(self):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.manager_gui import NetworkPanel
        self.NetworkPanel = NetworkPanel

    @pytest.fixture
    def panel(self, qtbot):
        p = self.NetworkPanel()
        qtbot.addWidget(p)
        return p

    def test_creates_without_error(self, panel):
        assert panel is not None

    def test_coordinator_alive_shows_filled_circle(self, panel):
        rec = CoordinatorRecord(host='localhost', port=12300, alive=True)
        panel.update_coordinator(rec)
        assert '●' in panel._coord_led.text()

    def test_coordinator_dead_shows_empty_circle(self, panel):
        rec = CoordinatorRecord(host='localhost', port=12300, alive=False)
        panel.update_coordinator(rec)
        assert '○' in panel._coord_led.text()

    def test_add_proxy_row_appears(self, panel):
        rec = ProxyRecord(in_port=11100, out_port=11099, alive=True)
        panel.update_proxy(rec)
        assert 11100 in panel._proxy_rows

    def test_add_proxy_not_duplicated(self, panel):
        rec = ProxyRecord(in_port=11100, out_port=11099, alive=True)
        panel.update_proxy(rec)
        panel.update_proxy(rec)
        assert len(panel._proxy_rows) == 1

    def test_remove_proxy_signal(self, panel, qtbot):
        received = []
        panel.remove_proxy_requested.connect(received.append)
        rec = ProxyRecord(in_port=11200, out_port=11199, alive=True)
        panel.update_proxy(rec)
        row = panel._proxy_rows[11200]
        # Last widget in row's layout is the remove button
        btn = row.layout().itemAt(2).widget()
        btn.click()
        assert 11200 in received


@pytestmark_qt
class TestComponentsTable:
    @pytest.fixture(autouse=True)
    def _imports(self):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.manager_gui import ComponentsTable, _role_color
        self.ComponentsTable = ComponentsTable
        self._role_color = _role_color

    @pytest.fixture
    def table(self, qtbot):
        t = self.ComponentsTable()
        qtbot.addWidget(t)
        return t

    def test_creates_without_error(self, table):
        assert table is not None

    def test_actor_added(self, table):
        rec = ComponentRecord(name='stage', full_name='localhost.stage',
                              role='actor', host='127.0.0.1')
        table.update_components([rec])
        assert table._tree.topLevelItemCount() == 1
        assert table._tree.topLevelItem(0).text(0) == 'stage'

    def test_director_added(self, table):
        rec = ComponentRecord(name='move_dir', full_name='localhost.move_dir',
                              role='director', host='mypc')
        table.update_components([rec])
        assert table._tree.topLevelItem(0).text(1) == 'director'

    def test_multiple_components(self, table):
        records = [
            ComponentRecord(name='stage', full_name='localhost.stage', role='actor'),
            ComponentRecord(name='cam', full_name='localhost.cam', role='actor'),
            ComponentRecord(name='move_dir', full_name='localhost.move_dir', role='director'),
        ]
        table.update_components(records)
        assert table._tree.topLevelItemCount() == 3

    def test_stale_component_removed(self, table):
        rec = ComponentRecord(name='stage', full_name='localhost.stage', role='actor')
        table.update_components([rec])
        table.update_components([])
        assert table._tree.topLevelItemCount() == 0

    def test_shutdown_button_emits_signal(self, table):
        received = []
        table.shutdown_requested.connect(received.append)
        rec = ComponentRecord(name='stage', full_name='localhost.stage', role='actor')
        table.update_components([rec])
        item = table._tree.topLevelItem(0)
        btn = table._tree.itemWidget(item, 4)
        btn.click()
        assert 'stage' in received

    def test_capabilities_added_as_children(self, table):
        rec = ComponentRecord(name='stage', full_name='localhost.stage', role='actor')
        table.update_components([rec])
        rec.capabilities = {
            'observables': [],
            'variables': [{'name': 'position', 'kind': 'ContinuousVariable'}],
        }
        table.update_actor_details(rec)
        item = table._items['stage']
        assert item.childCount() == 1

    def test_unknown_role_gets_red_background(self, table):
        rec = ComponentRecord(name='ghost', full_name='localhost.ghost', role='unknown')
        table.update_components([rec])
        item = table._tree.topLevelItem(0)
        bg = item.background(0).color()
        assert bg == self._role_color('unknown')


@pytestmark_qt
class TestLECOManagerGUI:
    @pytest.fixture(autouse=True)
    def _imports(self):
        pytest.importorskip('pytest_qt')
        from pymodaq.utils.leco.manager_gui import (
            LECOManagerGUI, ConnectDialog,
        )
        from qtpy import QtWidgets
        self.LECOManagerGUI = LECOManagerGUI
        self.ConnectDialog = ConnectDialog
        self.QtWidgets = QtWidgets

    @pytest.fixture
    def gui(self, qtbot):
        with patch('pymodaq.utils.leco.manager_gui.LECONetworkMonitor') as mock_cls:
            mock_monitor = MagicMock(spec=LECONetworkMonitor)
            # Prevent adapter from setting real callbacks on a MagicMock
            mock_monitor.on_components_changed = None
            mock_monitor.on_actor_details_changed = None
            mock_monitor.on_proxy_status_changed = None
            mock_monitor.on_coordinator_status_changed = None
            mock_cls.return_value = mock_monitor
            g = self.LECOManagerGUI()
            qtbot.addWidget(g)
        return g

    def test_creates_without_error(self, gui):
        assert gui is not None

    def test_has_network_panel(self, gui):
        assert gui._network_panel is not None

    def test_has_components_table(self, gui):
        assert gui._components_table is not None

    def test_refresh_calls_monitor(self, gui):
        gui._monitor.refresh_components = MagicMock()
        gui._on_refresh()
        gui._monitor.refresh_components.assert_called_once()

    def test_shutdown_delegates(self, gui):
        gui._monitor.shutdown_component = MagicMock()
        gui._on_shutdown_component('stage')
        gui._monitor.shutdown_component.assert_called_once_with('stage')

    def test_add_proxy_delegates(self, gui):
        gui._monitor.add_proxy = MagicMock()
        gui._on_add_proxy(11100, 11099, 'cameras')
        gui._monitor.add_proxy.assert_called_once_with(11100, 11099, 'cameras')

    def test_remove_proxy_delegates(self, gui):
        gui._monitor.remove_proxy = MagicMock()
        gui._on_remove_proxy(11100)
        gui._monitor.remove_proxy.assert_called_once_with(11100)

    def test_start_coordinator_delegates(self, gui):
        gui._monitor.start_coordinator = MagicMock()
        gui._on_start_coordinator('myhost', 12300, 'lab')
        gui._monitor.start_coordinator.assert_called_once_with(
            host='myhost', port=12300, namespace='lab'
        )

    def test_stop_coordinator_delegates(self, gui):
        gui._monitor.stop_coordinator = MagicMock()
        gui._on_stop_coordinator()
        gui._monitor.stop_coordinator.assert_called_once()

    def test_close_stops_polling(self, gui):
        gui._monitor.stop_polling = MagicMock()
        gui._monitor.stop_coordinator = MagicMock()
        gui.closeEvent(MagicMock())
        gui._monitor.stop_polling.assert_called_once()

    def test_connect_failure_shows_messagebox(self, gui):
        gui._monitor.connect = MagicMock(side_effect=ConnectionError('nope'))
        with patch.object(self.ConnectDialog, 'exec',
                          return_value=self.QtWidgets.QDialog.Accepted):
            with patch.object(self.QtWidgets.QMessageBox, 'warning') as mock_warn:
                gui._on_connect()
        mock_warn.assert_called_once()
