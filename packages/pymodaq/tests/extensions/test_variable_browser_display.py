"""Tests for Display column in VariableBrowserWidget.

Requires Qt.
"""
from __future__ import annotations

import sys
import pytest

qtpy = pytest.importorskip('qtpy')

import numpy as np
import xarray as xr
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _simple_xr_ctx(names=('scan/ch0', 'scan/ch1')):
    """Return a minimal name→xr.Dataset mapping."""
    return {
        name: xr.Dataset({'v': ('x', np.linspace(0, 1, 10))})
        for name in names
    }


@pytest.fixture
def browser(qapp):
    from pymodaq.extensions.data_mixer.gui.variable_browser import VariableBrowserWidget
    w = VariableBrowserWidget()
    return w


# ── Display column (Computed rows) ───────────────────────────────────────────

class TestDisplayColumn:

    def _add_computed(self, browser, name='result'):
        ds = xr.Dataset({'v': ('x', np.ones(5))})
        browser.add_computed(name, ds)
        return ds

    def test_computed_rows_have_display_checkbox(self, browser):
        self._add_computed(browser)
        item = browser._comp_root.child(0)
        assert item.checkState(browser._COL_DISP) == Qt.Unchecked

    def test_show_var_sig_emitted_on_check(self, browser, qtbot):
        self._add_computed(browser, 'res')
        item = browser._comp_root.child(0)

        with qtbot.waitSignal(browser.show_var_sig, timeout=1000) as blocker:
            item.setCheckState(browser._COL_DISP, Qt.Checked)
            browser._on_single_click(item, browser._COL_DISP)

        name, display = blocker.args
        assert name == 'res'
        assert display is True

    def test_get_display_names_empty_initially(self, browser):
        self._add_computed(browser, 'r')
        assert browser.get_display_names() == []

    def test_get_display_names_after_check(self, browser):
        self._add_computed(browser, 'r2')
        item = browser._comp_root.child(browser._comp_root.childCount() - 1)
        item.setCheckState(browser._COL_DISP, Qt.Checked)
        assert 'r2' in browser.get_display_names()

    def test_uncheck_display(self, browser):
        self._add_computed(browser, 'r3')
        item = browser._comp_root.child(browser._comp_root.childCount() - 1)
        item.setCheckState(browser._COL_DISP, Qt.Checked)
        browser.uncheck_display('r3')
        assert item.checkState(browser._COL_DISP) == Qt.Unchecked

    def test_update_computed_info(self, browser):
        ds_old = xr.Dataset({'v': ('x', np.ones(5))})
        browser.add_computed('upd', ds_old)
        ds_new = xr.Dataset({'v': ('x', np.ones(10))})
        browser.update_computed_info('upd', ds_new)
        # Find the item and check that info text changed
        for i in range(browser._comp_root.childCount()):
            item = browser._comp_root.child(i)
            if item.text(browser._COL_NAME) == 'upd':
                info = item.text(browser._COL_INFO)
                assert '10' in info   # new shape
                break


# ── Computed variable lifecycle ───────────────────────────────────────────────

class TestComputedLifecycle:

    def _ds(self, size=5):
        return xr.Dataset({'v': ('x', np.ones(size))})

    def test_has_computed_false_before_add(self, browser):
        assert browser.has_computed('never_added') is False

    def test_has_computed_true_after_add(self, browser):
        browser.add_computed('c1', self._ds())
        assert browser.has_computed('c1') is True

    def test_add_computed_idempotent_updates_info(self, browser):
        browser.add_computed('c2', self._ds(5))
        browser.add_computed('c2', self._ds(99))
        # Only one child with name 'c2'
        found = [browser._comp_root.child(i)
                 for i in range(browser._comp_root.childCount())
                 if browser._comp_root.child(i).text(browser._COL_NAME) == 'c2']
        assert len(found) == 1
        assert '99' in found[0].text(browser._COL_INFO)

    def test_remove_computed_removes_item(self, browser):
        browser.add_computed('c3', self._ds())
        assert browser.has_computed('c3')
        browser.remove_computed('c3')
        assert not browser.has_computed('c3')

    def test_remove_computed_absent_name_is_noop(self, browser):
        browser.remove_computed('does_not_exist')   # must not raise

    def test_clear_computed_removes_all(self, browser):
        browser.add_computed('ca', self._ds())
        browser.add_computed('cb', self._ds())
        browser.clear_computed()
        assert browser._comp_root.childCount() == 0


# ── H5 tree population ────────────────────────────────────────────────────────

class TestLoadH5:

    def _ctx(self, names):
        return {name: None for name in names}

    def test_flat_single_scan_creates_items(self, browser):
        browser.load_h5(self._ctx(['Scan000/Det/CH0', 'Scan000/Det/CH1']))
        assert browser._h5_root.childCount() == 2

    def test_info_dict_populates_info_column(self, browser):
        names = ['Scan000/Det/CH0']
        info = {'Scan000/Det/CH0': 'float32 (10,)'}
        browser.load_h5(self._ctx(names), info=info)
        item = browser._h5_root.child(0)
        assert item.text(browser._COL_INFO) == 'float32 (10,)'

    def test_multi_scan_creates_headers(self, browser):
        browser.load_h5(self._ctx(['Scan000/Det/CH0', 'Scan001/Det/CH0']))
        # Two scan-header children under h5_root
        assert browser._h5_root.childCount() == 2

    def test_multi_scan_datasets_under_headers(self, browser):
        browser.load_h5(self._ctx(['Scan000/Det/CH0', 'Scan001/Det/CH0']))
        header0 = browser._h5_root.child(0)
        assert header0.childCount() == 1   # one dataset per scan

    def test_reload_replaces_previous_tree(self, browser):
        browser.load_h5(self._ctx(['Scan000/A', 'Scan000/B', 'Scan000/C']))
        browser.load_h5(self._ctx(['Scan000/X']))
        assert browser._h5_root.childCount() == 1

    def test_loaded_ds_builds_leaf_nodes(self, browser):
        ds = xr.Dataset({'ch0': ('time', np.arange(5)),
                         'ch1': ('time', np.arange(5))})
        browser.load_h5({'Scan000/Det': ds})
        ds_item = browser._h5_root.child(0)
        assert ds_item.childCount() == 2   # one leaf per data_var


# ── update_h5_info (lazy leaf population) ─────────────────────────────────────

class TestUpdateH5Info:

    def test_populates_info_column(self, browser):
        browser.load_h5({'Scan000/Det/CH0': None}, info={'Scan000/Det/CH0': '?'})
        ds = xr.Dataset({'v': ('x', np.ones(7))})
        browser.update_h5_info('Scan000/Det/CH0', ds)
        item = next(browser._iter_h5_ds_items())
        assert '7' in item.text(browser._COL_INFO)

    def test_adds_leaf_nodes_when_absent(self, browser):
        browser.load_h5({'Scan000/Det/CH0': None})
        ds = xr.Dataset({'v': ('x', np.ones(3)), 'w': ('x', np.ones(3))})
        browser.update_h5_info('Scan000/Det/CH0', ds)
        item = next(browser._iter_h5_ds_items())
        assert item.childCount() == 2

    def test_noop_on_none_ds(self, browser):
        browser.load_h5({'Scan000/Det/CH0': None})
        browser.update_h5_info('Scan000/Det/CH0', None)   # must not raise


# ── Filter ────────────────────────────────────────────────────────────────────

class TestFilter:

    def _setup(self, browser):
        browser.load_h5({'Scan000/alpha': None, 'Scan000/beta': None})
        browser.add_computed('comp_alpha', xr.Dataset({'v': ('x', np.ones(3))}))

    def test_empty_filter_shows_all_h5(self, browser):
        self._setup(browser)
        browser.set_filter('')
        for i in range(browser._h5_root.childCount()):
            assert not browser._h5_root.child(i).isHidden()

    def test_filter_hides_non_matching_h5(self, browser):
        self._setup(browser)
        browser.set_filter('alpha')
        items = [browser._h5_root.child(i)
                 for i in range(browser._h5_root.childCount())]
        names = [it.text(browser._COL_NAME) for it in items if not it.isHidden()]
        assert all('alpha' in n for n in names)

    def test_filter_hides_non_matching_computed(self, browser):
        self._setup(browser)
        browser.set_filter('zzz')
        for i in range(browser._comp_root.childCount()):
            assert browser._comp_root.child(i).isHidden()

    def test_filter_shows_matching_computed(self, browser):
        self._setup(browser)
        browser.set_filter('alpha')
        visible = [browser._comp_root.child(i)
                   for i in range(browser._comp_root.childCount())
                   if not browser._comp_root.child(i).isHidden()]
        assert len(visible) == 1
        assert visible[0].text(browser._COL_NAME) == 'comp_alpha'


# ── Double-click → insert_ref_sig ─────────────────────────────────────────────

class TestDoubleClick:

    def test_h5_ds_emits_braced_name(self, browser, qtbot):
        browser.load_h5({'Scan000/Det/CH0': None})
        item = next(browser._iter_h5_ds_items())
        with qtbot.waitSignal(browser.insert_ref_sig, timeout=1000) as sig:
            browser._on_double_click(item, browser._COL_NAME)
        assert sig.args[0] == '{Scan000/Det/CH0}'

    def test_h5_var_emits_name_plus_var(self, browser, qtbot):
        ds = xr.Dataset({'ch0': ('x', np.ones(3))})
        browser.load_h5({'Scan000/Det': ds})
        ds_item = browser._h5_root.child(0)
        leaf = ds_item.child(0)
        with qtbot.waitSignal(browser.insert_ref_sig, timeout=1000) as sig:
            browser._on_double_click(leaf, browser._COL_NAME)
        assert sig.args[0] == '{Scan000/Det}["ch0"]'

    def test_computed_emits_braced_name(self, browser, qtbot):
        browser.add_computed('myres', xr.Dataset({'v': ('x', np.ones(3))}))
        item = browser._find_computed_item('myres')
        with qtbot.waitSignal(browser.insert_ref_sig, timeout=1000) as sig:
            browser._on_double_click(item, browser._COL_NAME)
        assert sig.args[0] == '{myres}'
