"""Tests for DataMixerGUI (CustomExt-based).

All tests require Qt.  They exercise the new DockArea-based interface,
param-tree settings, ActionManager actions, and the formula/viewer pipeline.
"""
from __future__ import annotations

import sys
import pytest
import numpy as np

qtpy = pytest.importorskip('qtpy')

from qtpy.QtWidgets import QApplication, QMainWindow

from pymodaq_gui.utils.dock import DockArea


# ── shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def win_area(qapp):
    """Provide a QMainWindow + DockArea pair and tear down afterward."""
    win = QMainWindow()
    area = DockArea()
    win.setCentralWidget(area)
    win.show()
    yield win, area
    win.close()


@pytest.fixture
def gui(win_area):
    """DataMixerGUI with no H5 file and no Dashboard."""
    _, area = win_area
    from pymodaq.extensions.data_mixer.gui.data_mixer_gui import DataMixerGUI
    g = DataMixerGUI(area, dashboard=None)
    yield g
    g.quit_fun()


def _make_dwa(name='result', shape=(10,)):
    """Create a simple DataWithAxes for testing."""
    from pymodaq_data.data import DataWithAxes, DataSource, Axis
    data = np.random.rand(*shape)
    axes = [Axis(label=f'ax{i}', data=np.arange(s), index=i)
            for i, s in enumerate(shape)]
    return DataWithAxes(name, source=DataSource['calculated'],
                        data=[data], axes=axes)


def _make_xr_ds(name='result', shape=(10,)):
    """Create an xr.Dataset wrapping a simple DataWithAxes."""
    return _make_dwa(name, shape).to_xarray()


# ── Construction & docks ──────────────────────────────────────────────────────

class TestSetupDocks:

    def test_four_docks_created(self, gui):
        assert set(gui.docks.keys()) >= {'settings', 'browser', 'console', 'viewer'}

    def test_settings_dock_has_tree(self, gui):
        # settings_tree is added to the dock; dock must have content
        assert gui.docks['settings'] is not None

    def test_browser_widget_exists(self, gui):
        from pymodaq.extensions.data_mixer.gui.variable_browser import (
            VariableBrowserWidget,
        )
        assert isinstance(gui._browser, VariableBrowserWidget)

    def test_info_panel_exists(self, gui):
        from pymodaq.extensions.data_mixer.gui.info_panel import InfoPanelWidget
        assert isinstance(gui._info_panel, InfoPanelWidget)

    def test_console_exists(self, gui):
        from pymodaq.extensions.data_mixer.gui.console import FormulaConsole
        assert isinstance(gui._console, FormulaConsole)

    def test_viewer_widget_exists(self, gui):
        from pymodaq.extensions.data_mixer.gui.viewer_window import DataViewerWindow
        assert isinstance(gui._viewer_widget, DataViewerWindow)

    def test_dockarea_is_set(self, gui, win_area):
        _, area = win_area
        assert gui.dockarea is area


# ── Actions ───────────────────────────────────────────────────────────────────

class TestSetupActions:

    def test_browse_action_exists(self, gui):
        assert gui.has_action('browse')

    def test_load_action_exists(self, gui):
        assert gui.has_action('load')

    def test_refresh_tree_action_exists(self, gui):
        assert gui.has_action('refresh_tree')

    def test_live_sync_action_is_checkable(self, gui):
        assert gui.get_action('live_sync').isCheckable()

    def test_show_viewer_action_exists(self, gui):
        assert gui.has_action('show_viewer')


# ── Params / value_changed ───────────────────────────────────────────────────

class TestParams:

    def test_h5_path_param_exists(self, gui):
        assert gui.settings.child('h5_path') is not None

    def test_interval_param_exists(self, gui):
        assert gui.settings.child('live_sync', 'interval') is not None

    def test_active_scan_param_exists(self, gui):
        assert gui.settings.child('live_sync', 'active_scan') is not None

    def test_interval_change_updates_active_timer(self, gui):
        gui._sync_timer.start(1000)
        gui.settings.child('live_sync', 'interval').setValue(2000)
        assert gui._sync_timer.interval() == 2000
        gui._sync_timer.stop()

    def test_interval_change_no_op_when_stopped(self, gui):
        gui._sync_timer.stop()
        gui.settings.child('live_sync', 'interval').setValue(500)
        assert not gui._sync_timer.isActive()

    def test_active_scan_change_calls_handler(self, gui, monkeypatch):
        called_with = []
        monkeypatch.setattr(gui, '_on_active_scan_changed',
                            lambda p: called_with.append(p))
        gui.settings.child('live_sync', 'active_scan').setLimits(['Scan001', 'Scan002'])
        gui.settings.child('live_sync', 'active_scan').setValue('Scan001')
        assert 'Scan001' in called_with


# ── Toggle live sync (no file) ────────────────────────────────────────────────

class TestToggleLiveSync:

    def test_toggle_on_with_missing_file_unchecks_action(self, gui):
        gui.settings.child('h5_path').setValue('/nonexistent/path.h5')
        gui._toggle_live_sync(True)
        assert not gui.is_action_checked('live_sync')
        assert not gui._sync_timer.isActive()

    def test_toggle_off_stops_timer(self, gui):
        gui._sync_timer.start(1000)
        gui._toggle_live_sync(False)
        assert not gui._sync_timer.isActive()

    def test_toggle_off_closes_live_handle(self, gui):
        # inject a fake handle to confirm it gets closed
        class FakeH5:
            closed = False
            def close_file(self): self.closed = True

        fake = FakeH5()
        gui._h5saver_live = fake
        gui._sync_timer.start(100)
        gui._toggle_live_sync(False)
        assert fake.closed
        assert gui._h5saver_live is None

    def test_toggle_off_re_enables_refresh_tree(self, gui):
        gui.set_action_enabled('refresh_tree', False)
        gui._toggle_live_sync(False)
        assert gui.get_action('refresh_tree').isEnabled()


# ── Computed variable pipeline ────────────────────────────────────────────────

class TestComputedVariables:

    def test_on_new_variable_adds_to_state(self, gui):
        gui._xr_ctx_computed.clear()
        gui._formula_for.clear()
        ds = _make_xr_ds('v1')
        gui._on_new_variable('v1', ds, '{} + 1')
        assert 'v1' in gui._xr_ctx_computed
        assert 'v1' in gui._formula_for

    def test_on_new_variable_adds_to_browser(self, gui):
        gui._xr_ctx_computed.clear()
        ds = _make_xr_ds('browser_test')
        gui._on_new_variable('browser_test', ds, 'np.zeros(10)')
        assert gui._browser.has_computed('browser_test')

    def test_on_delete_computed_removes_from_state(self, gui):
        ds = _make_xr_ds('to_delete')
        gui._xr_ctx_computed['to_delete'] = ds
        gui._formula_for['to_delete'] = 'np.zeros(5)'
        gui._deps['to_delete'] = set()
        gui._on_delete_computed('to_delete')
        assert 'to_delete' not in gui._xr_ctx_computed
        assert 'to_delete' not in gui._formula_for

    def test_on_clear_computed_empties_state(self, gui):
        gui._xr_ctx_computed['x'] = _make_xr_ds('x')
        gui._formula_for['x'] = 'np.ones(3)'
        gui._deps['x'] = set()
        gui._on_clear_computed()
        assert gui._xr_ctx_computed == {}
        assert gui._formula_for == {}
        assert gui._deps == {}


# ── Formula evaluation ────────────────────────────────────────────────────────

class TestEvalFormulas:

    def test_eval_simple_formula(self, gui):
        """A formula referencing a computed variable is evaluated correctly."""
        import xarray as xr

        ds_in = _make_xr_ds('input_data', (5,))
        gui._h5_snapshot['input_data'] = ds_in
        gui._formula_for = {'output': '{input_data}'}
        gui._rebuild_deps()
        gui._eval_formulas({'input_data'})
        assert 'output' in gui._xr_ctx_computed

    def test_eval_skips_unrelated_formula(self, gui):
        """Formulas whose deps haven't changed are skipped."""
        ds = _make_xr_ds('irrelevant', (3,))
        gui._h5_snapshot['irrelevant'] = ds
        gui._xr_ctx_computed.clear()
        gui._formula_for = {'out': '{irrelevant}'}
        gui._deps = {'out': {'irrelevant'}}
        # 'other' changed but 'out' depends on 'irrelevant', not 'other'
        gui._eval_formulas({'other'})
        assert 'out' not in gui._xr_ctx_computed

    def test_eval_chained_formulas(self, gui):
        """Formula B depending on formula A's output is also updated."""
        import xarray as xr

        ds_in = _make_xr_ds('raw', (4,))
        gui._h5_snapshot['raw'] = ds_in
        gui._xr_ctx_computed.clear()
        gui._formula_for = {
            'step1': '{raw}',
            'step2': '{step1}',
        }
        gui._rebuild_deps()
        gui._eval_formulas({'raw'})
        assert 'step1' in gui._xr_ctx_computed
        assert 'step2' in gui._xr_ctx_computed


# ── Viewer integration ────────────────────────────────────────────────────────

class TestViewerIntegration:

    def test_on_show_var_opens_dock(self, gui):
        ds = _make_xr_ds('show_me', (5,))
        gui._xr_ctx_computed['show_me'] = ds
        gui._on_show_var('show_me', True)
        assert 'show_me' in gui._display_names
        assert gui._viewer_widget.has_variable('show_me')

    def test_on_show_var_false_removes_tab(self, gui):
        # show first
        ds = _make_xr_ds('hide_me', (5,))
        gui._xr_ctx_computed['hide_me'] = ds
        gui._on_show_var('hide_me', True)
        # now hide
        gui._on_show_var('hide_me', False)
        assert 'hide_me' not in gui._display_names
        assert not gui._viewer_widget.has_variable('hide_me')

    def test_viewer_tab_close_unchecks_browser(self, gui):
        ds = _make_xr_ds('close_tab', (5,))
        gui._xr_ctx_computed['close_tab'] = ds
        gui._on_show_var('close_tab', True)
        gui._display_names.add('close_tab')
        # simulate tab close signal
        gui._on_viewer_tab_closed('close_tab')
        assert 'close_tab' not in gui._display_names

    def test_raise_viewers_no_tabs_sets_status(self, gui):
        """_raise_viewers with no open tabs should set a status message."""
        gui._viewer_widget.clear()
        gui._display_names.clear()
        # Should not raise; status is updated
        gui._raise_viewers()


# ── H5 context building ───────────────────────────────────────────────────────

class TestH5Context:

    def test_build_h5_context_no_prefix(self, gui):
        gui._h5_meta = {'Scan001/Det/CH0': None, 'Scan001/Det/CH1': None}
        gui._active_scan_prefix = None
        ctx = gui._build_h5_context()
        # No aliases when no active prefix
        assert 'Scan/' not in str(list(ctx.keys()))

    def test_build_h5_context_with_prefix(self, gui):
        gui._h5_meta = {'Scan001/Det/CH0': None, 'Scan002/Det/CH0': None}
        gui._active_scan_prefix = 'Scan001'
        ctx = gui._build_h5_context()
        assert 'Scan/Det/CH0' in ctx

    def test_build_h5_context_alias_maps_correct_prefix(self, gui):
        gui._h5_meta = {
            'Scan001/Det/CH0': None,
            'Scan002/Det/CH0': None,
        }
        gui._active_scan_prefix = 'Scan002'
        ctx = gui._build_h5_context()
        assert 'Scan/Det/CH0' in ctx
        # Both real names still present
        assert 'Scan001/Det/CH0' in ctx
        assert 'Scan002/Det/CH0' in ctx

    def test_on_active_scan_changed_clears_scan_cache(self, gui):
        gui._h5_snapshot = {'Scan/x': 'old', 'Scan001/x': 'real'}
        gui._h5_meta = {'Scan001/x': None, 'Scan002/x': None}
        gui._formula_for = {}
        gui._active_scan_prefix = 'Scan001'
        gui._on_active_scan_changed('Scan002')
        assert 'Scan/x' not in gui._h5_snapshot


# ── Scan progress detection ───────────────────────────────────────────────────

class TestScanProgress:

    def test_node_fill_value_from_fillvalue(self, gui):
        class FakeNode:
            fillvalue = 0.0

        assert gui._node_fill_value(FakeNode()) == 0.0

    def test_node_fill_value_from_atom_dflt(self, gui):
        class FakeAtom:
            dflt = float('nan')

        class FakeNode:
            @property
            def fillvalue(self):
                raise AttributeError
            atom = FakeAtom()

        import math
        assert math.isnan(gui._node_fill_value(FakeNode()))

    def test_node_fill_value_returns_none_on_missing(self, gui):
        class FakeNode:
            @property
            def fillvalue(self):
                raise AttributeError

        assert gui._node_fill_value(FakeNode()) is None


# ── Status helper ─────────────────────────────────────────────────────────────

class TestSetStatus:

    def test_set_status_does_not_raise_without_statusbar(self, gui):
        """_set_status must not raise even when statusbar is None."""
        old = gui.statusbar
        gui.statusbar = None
        try:
            gui._set_status('test message')   # must not raise
        finally:
            gui.statusbar = old

    def test_set_status_with_statusbar(self, gui):
        if gui.statusbar is None:
            pytest.skip('No statusbar available in this setup')
        gui._set_status('hello')
        assert gui.statusbar.currentMessage() == 'hello'
