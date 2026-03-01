"""Tests for DataMixerGUI dependency-map building and H5SaverLowLevel helpers.

Qt is required to instantiate DataMixerGUI (it now inherits from CustomExt).
"""
from __future__ import annotations

import pytest

qtpy = pytest.importorskip('qtpy')   # skip entire module if Qt absent

import sys
from qtpy.QtWidgets import QApplication, QMainWindow

from pymodaq_gui.utils.dock import DockArea


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ── helpers ────────────────────────────────────────────────────────────────────

@pytest.fixture
def gui(qapp):
    """Minimal DataMixerGUI on an in-process DockArea (no Dashboard)."""
    win = QMainWindow()
    area = DockArea()
    win.setCentralWidget(area)
    from pymodaq.extensions.data_mixer.gui.data_mixer_gui import DataMixerGUI
    g = DataMixerGUI(area, dashboard=None)
    yield g
    g.quit_fun()


# ── H5SaverLowLevel.open_for_reading tests ─────────────────────────────────────

class TestOpenForReading:
    """Tests for H5SaverLowLevel.open_for_reading()."""

    def test_nonexistent_file_raises(self, qapp, tmp_path):
        from pymodaq_data.h5modules.saving import H5SaverLowLevel
        with pytest.raises(Exception):
            H5SaverLowLevel.open_for_reading(tmp_path / 'does_not_exist.h5')

    def test_invalid_file_raises(self, qapp, tmp_path):
        """A file that exists but is not valid HDF5 must raise."""
        from pymodaq_data.h5modules.saving import H5SaverLowLevel
        bad = tmp_path / 'bad.h5'
        bad.write_bytes(b'not hdf5')
        with pytest.raises(Exception):
            H5SaverLowLevel.open_for_reading(bad)

    def test_returns_saver_and_bool(self, qapp, tmp_path):
        """A real H5 file should return (H5SaverLowLevel, bool)."""
        import h5py
        from pymodaq_data.h5modules.saving import H5SaverLowLevel
        h5path = tmp_path / 'valid.h5'
        with h5py.File(h5path, 'w') as f:
            f.create_dataset('data', data=[1, 2, 3])
        saver, is_swmr = H5SaverLowLevel.open_for_reading(h5path)
        try:
            assert isinstance(saver, H5SaverLowLevel)
            assert isinstance(is_swmr, bool)
            assert saver.isopen()
        finally:
            saver.close_file()


# ── DataMixerGUI._rebuild_deps tests ──────────────────────────────────────────

class TestDataMixerGUIDeps:
    """Test _rebuild_deps and dependency tracking in DataMixerGUI."""

    def test_rebuild_deps_single_formula(self, gui):
        gui._formula_for = {'out': '{scan/data} + 1'}
        gui._rebuild_deps()
        assert gui._deps == {'out': {'scan/data'}}

    def test_rebuild_deps_multiple_inputs(self, gui):
        gui._formula_for = {'out': '{a} * {b} + {c}'}
        gui._rebuild_deps()
        assert gui._deps == {'out': {'a', 'b', 'c'}}

    def test_rebuild_deps_no_refs(self, gui):
        gui._formula_for = {'out': '1 + 2'}
        gui._rebuild_deps()
        assert gui._deps == {'out': set()}

    def test_rebuild_deps_multiple_formulas(self, gui):
        gui._formula_for = {'a': '{x}', 'b': '{x} + {a}'}
        gui._rebuild_deps()
        assert gui._deps['a'] == {'x'}
        assert gui._deps['b'] == {'x', 'a'}

    def test_interval_value_changed_updates_active_timer(self, gui):
        """Setting the interval param while timer runs updates the interval."""
        gui._sync_timer.start(1000)
        # Simulate a value_changed call for the interval param
        gui.settings.child('live_sync', 'interval').setValue(2500)
        assert gui._sync_timer.interval() == 2500
        gui._sync_timer.stop()

    def test_interval_value_changed_no_op_when_timer_stopped(self, gui):
        """Changing interval while timer is stopped doesn't start it."""
        gui._sync_timer.stop()
        gui.settings.child('live_sync', 'interval').setValue(3000)
        assert not gui._sync_timer.isActive()
