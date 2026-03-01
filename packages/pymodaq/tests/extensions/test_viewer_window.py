"""Tests for DataViewerWindow.

Requires Qt.
"""
from __future__ import annotations

import sys
import pytest

qtpy = pytest.importorskip('qtpy')

import numpy as np
from qtpy.QtWidgets import QApplication


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _dwa_1d(name='sig', n=20):
    from pymodaq_data.data import DataWithAxes, DataSource, Axis
    return DataWithAxes(
        name, source=DataSource['calculated'],
        data=[np.linspace(0, 1, n)],
        axes=[Axis(label='x', data=np.linspace(0, 1, n), index=0)],
    )


def _dwa_0d(name='scalar'):
    from pymodaq_data.data import DataWithAxes, DataSource
    return DataWithAxes(name, source=DataSource['calculated'],
                        data=[np.array([3.14])])


@pytest.fixture
def win(qapp):
    from pymodaq.extensions.data_mixer.gui.viewer_window import DataViewerWindow
    w = DataViewerWindow()
    yield w
    w.close()


class TestDataViewerWindow:

    def test_initially_empty(self, win):
        assert win.variable_names == []
        assert win._tabs.count() == 0

    def test_show_variable_creates_tab(self, win):
        dwa = _dwa_1d('sig1')
        win.show_variable('sig1', dwa)
        assert win.has_variable('sig1')
        assert win._tabs.count() == 1
        assert win._tabs.tabText(0) == 'sig1'

    def test_show_two_variables_two_tabs(self, win):
        win.clear()
        win.show_variable('a', _dwa_1d('a'))
        win.show_variable('b', _dwa_1d('b'))
        assert win._tabs.count() == 2
        assert set(win.variable_names) == {'a', 'b'}

    def test_show_variable_switches_to_tab(self, win):
        win.clear()
        win.show_variable('first', _dwa_1d('first'))
        win.show_variable('second', _dwa_1d('second'))
        win.show_variable('first', _dwa_1d('first'))  # re-show
        assert win._tabs.currentIndex() == win._tab_index('first')

    def test_update_existing_tab(self, win):
        win.clear()
        win.show_variable('x', _dwa_1d('x', n=5))
        # Should not raise or create a second tab
        win.update('x', _dwa_1d('x', n=10))
        assert win._tabs.count() == 1

    def test_update_absent_name_is_noop(self, win):
        win.clear()
        win.update('nonexistent', _dwa_1d('nonexistent'))   # must not raise
        assert win._tabs.count() == 0

    def test_remove_variable(self, win):
        win.clear()
        win.show_variable('r', _dwa_1d('r'))
        win.remove_variable('r')
        assert not win.has_variable('r')
        assert win._tabs.count() == 0

    def test_remove_absent_name_is_noop(self, win):
        win.clear()
        win.remove_variable('ghost')   # must not raise

    def test_clear_removes_all_tabs(self, win):
        win.clear()
        win.show_variable('p', _dwa_1d('p'))
        win.show_variable('q', _dwa_1d('q'))
        win.clear()
        assert win._tabs.count() == 0
        assert win.variable_names == []

    def test_tab_closed_sig_emitted(self, win, qtbot):
        win.clear()
        win.show_variable('close_me', _dwa_1d('close_me'))
        with qtbot.waitSignal(win.tab_closed_sig, timeout=1000) as blocker:
            win._on_tab_close(0)
        assert blocker.args[0] == 'close_me'
        assert not win.has_variable('close_me')

    def test_0d_variable_accepted(self, win):
        win.clear()
        dwa = _dwa_0d('scalar')
        win.show_variable('scalar', dwa)
        assert win.has_variable('scalar')
