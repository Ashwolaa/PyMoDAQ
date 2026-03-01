"""Tests for DataMixerGUI dependency-map building and H5SaverLowLevel helpers.

Qt is required to instantiate DataMixerGUI (it inherits QWidget).
"""
from __future__ import annotations

import pytest

qtpy = pytest.importorskip('qtpy')   # skip entire module if Qt absent

from qtpy.QtWidgets import QApplication  # noqa: E402
import sys


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_gui(qapp):
    from pymodaq.extensions.data_mixer.gui.data_mixer_gui import DataMixerGUI
    # Do not pass h5_path — avoids trying to open a file during construction
    return DataMixerGUI()


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
        # Create a minimal valid H5 file
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

    def test_rebuild_deps_single_formula(self, qapp):
        gui = _make_gui(qapp)
        gui._formula_for = {'out': '{scan/data} + 1'}
        gui._rebuild_deps()
        assert gui._deps == {'out': {'scan/data'}}

    def test_rebuild_deps_multiple_inputs(self, qapp):
        gui = _make_gui(qapp)
        gui._formula_for = {'out': '{a} * {b} + {c}'}
        gui._rebuild_deps()
        assert gui._deps == {'out': {'a', 'b', 'c'}}

    def test_rebuild_deps_no_refs(self, qapp):
        gui = _make_gui(qapp)
        gui._formula_for = {'out': '1 + 2'}
        gui._rebuild_deps()
        assert gui._deps == {'out': set()}

    def test_rebuild_deps_multiple_formulas(self, qapp):
        gui = _make_gui(qapp)
        gui._formula_for = {'a': '{x}', 'b': '{x} + {a}'}
        gui._rebuild_deps()
        assert gui._deps['a'] == {'x'}
        assert gui._deps['b'] == {'x', 'a'}

    def test_interval_changes_active_timer(self, qapp):
        gui = _make_gui(qapp)
        gui._sync_timer.start(1000)
        gui._on_interval_changed(2500)
        assert gui._sync_timer.interval() == 2500
        gui._sync_timer.stop()
