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
