"""Tests for _FallbackEditor autocomplete modes M1–M5.

Requires Qt (the editor inherits QPlainTextEdit).
``_detect_completion`` accepts an optional ``_text`` parameter so we can
exercise the regex state-machine directly without setting up a real cursor.
"""
from __future__ import annotations

import sys
import pytest
import numpy as np

qtpy = pytest.importorskip('qtpy')

from qtpy.QtWidgets import QApplication

from pymodaq.extensions.data_mixer.gui.console import _FallbackEditor


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


# ── helpers ───────────────────────────────────────────────────────────────────

def _editor(h5_ctx=None, computed=None, h5_loader=None, qapp=None):
    """Instantiate _FallbackEditor and inject context without needing signals."""
    ed = _FallbackEditor.__new__(_FallbackEditor)
    ed._h5_ctx = h5_ctx or {}
    ed._computed = computed or {}
    ed._all_names = list(ed._h5_ctx) + list(ed._computed)
    ed._h5_loader = h5_loader
    return ed


def _ds(data_vars: dict, coords_per_var: dict | None = None):
    """Return a minimal xr.Dataset-like stub for autocomplete tests."""
    import xarray as xr
    coords_per_var = coords_per_var or {}
    arrays = {}
    for var, dims in data_vars.items():
        coord_kwargs = {d: np.arange(3) for d in dims}
        arrays[var] = xr.DataArray(np.zeros([3] * len(dims)),
                                   dims=dims, coords=coord_kwargs)
    ds = xr.Dataset(arrays)
    return ds


# ── M1: @ trigger (inserts {name}) ───────────────────────────────────────────

class TestM1:

    def test_partial_name(self, qapp):
        ed = _editor({'Scan001/Det/CH00': None, 'Scan001/Det/CH01': None})
        mode, prefix, cands = ed._detect_completion('@CH0')
        assert mode == 'M1'
        assert 'Scan001/Det/CH00' in cands

    def test_empty_prefix_returns_all_names(self, qapp):
        ed = _editor({'a': None, 'b': None})
        mode, _, cands = ed._detect_completion('@')
        assert mode == 'M1'
        assert {'a', 'b'} <= set(cands)

    def test_includes_computed_names(self, qapp):
        ed = _editor(h5_ctx={'raw': None}, computed={'result': _ds({'result': ['x']})})
        mode, _, cands = ed._detect_completion('@res')
        assert mode == 'M1'
        assert 'result' in cands

    def test_no_trigger_on_open_brace(self, qapp):
        """Opening { alone must not trigger M1 (dict literal safety)."""
        ed = _editor({'a': None, 'b': None})
        mode, _, _ = ed._detect_completion("d = {'key': ")
        assert mode == 'NONE'


# ── M2: after {name}[" ───────────────────────────────────────────────────────

class TestM2:

    def test_loaded_h5_ds_returns_data_vars(self, qapp):
        ds = _ds({'CH00': ['dim_0'], 'CH01': ['dim_0']})
        ed = _editor({'Scan001/Det/Data1D/CH00': ds})
        mode, prefix, cands = ed._detect_completion(
            '{Scan001/Det/Data1D/CH00}["')
        assert mode == 'M2'
        assert 'CH00' in cands and 'CH01' in cands

    def test_unloaded_ds_infers_channel_from_path(self, qapp):
        """When dataset is None (not yet loaded), infer channel from path tail."""
        ed = _editor({'Scan001/Det/Data1D/CH00': None})
        mode, _, cands = ed._detect_completion(
            '{Scan001/Det/Data1D/CH00}["')
        assert mode == 'M2'
        assert cands == ['CH00']

    def test_unloaded_filters_when_prefix_no_match(self, qapp):
        ed = _editor({'Scan001/Det/Data1D/CH00': None})
        mode, _, cands = ed._detect_completion(
            '{Scan001/Det/Data1D/CH00}["CH01')
        # CH00 does not start with CH01
        assert mode == 'M2'
        assert 'CH00' not in cands

    def test_computed_var_resolves_data_vars(self, qapp):
        """Computed dataset data-vars should appear in M2."""
        ds = _ds({'my_result': ['x']})
        ed = _editor(computed={'my_result': ds})
        mode, _, cands = ed._detect_completion('{my_result}["')
        assert mode == 'M2'
        assert 'my_result' in cands

    def test_partial_prefix_filters_candidates(self, qapp):
        ds = _ds({'CH00': ['d'], 'CH01': ['d'], 'timestamps': ['d']})
        ed = _editor({'path/ds': ds})
        mode, _, cands = ed._detect_completion('{path/ds}["CH')
        assert mode == 'M2'
        assert all('ch' in c.lower() for c in cands)
        assert 'timestamps' not in cands

    def test_scan_alias_unloaded_infers_correctly(self, qapp):
        """Scan/ alias paths should also produce the correct channel name."""
        ed = _editor({'Scan/Det/Data1D/CH02': None})
        mode, _, cands = ed._detect_completion(
            '{Scan/Det/Data1D/CH02}["')
        assert mode == 'M2'
        assert cands == ['CH02']


# ── M2b: after {name}["var"][" ───────────────────────────────────────────────

class TestM2b:

    def test_loaded_h5_ds_returns_coords(self, qapp):
        ds = _ds({'CH00': ['x', 'y']})
        ed = _editor({'Scan/Det/CH00': ds})
        mode, _, cands = ed._detect_completion(
            '{Scan/Det/CH00}["CH00"]["')
        assert mode == 'M2b'
        assert 'x' in cands and 'y' in cands

    def test_computed_var_coords(self, qapp):
        ds = _ds({'result': ['time', 'space']})
        ed = _editor(computed={'result': ds})
        mode, _, cands = ed._detect_completion('{result}["result"]["')
        assert mode == 'M2b'
        assert 'time' in cands


# ── M3: after }. / ]. / ). ───────────────────────────────────────────────────

class TestM3:

    def test_after_bracket_close_suggests_xr_methods(self, qapp):
        ed = _editor()
        mode, _, cands = ed._detect_completion('{x}["CH00"].me')
        assert mode == 'M3'
        assert any('mean' in c for c in cands)

    def test_after_paren_close(self, qapp):
        ed = _editor()
        mode, _, cands = ed._detect_completion('{x}.mean("d").su')
        assert mode == 'M3'
        assert any('sum' in c for c in cands)


# ── M4: dimension name inside .mean("…) etc. ─────────────────────────────────

class TestM4:

    def test_loaded_computed_proposes_dims(self, qapp):
        ds = _ds({'result': ['x', 'y']})
        ed = _editor(computed={'result': ds})
        mode, _, cands = ed._detect_completion('{result}["result"].mean("')
        assert mode == 'M4'
        assert 'x' in cands and 'y' in cands

    def test_loaded_h5_proposes_dims(self, qapp):
        ds = _ds({'CH00': ['dim_0', 'dim_1']})
        ed = _editor({'Scan/Det/CH00': ds})
        mode, _, cands = ed._detect_completion('{Scan/Det/CH00}["CH00"].mean("')
        assert mode == 'M4'
        assert 'dim_0' in cands and 'dim_1' in cands

    def test_unloaded_h5_uses_loader(self, qapp):
        """When the dataset is None, the loader is called to resolve dims."""
        ds = _ds({'CH00': ['scan_axis', 'det_axis']})
        loader_calls = []

        def fake_loader(name):
            loader_calls.append(name)
            return ds

        ed = _editor({'Scan/Det/CH00': None}, h5_loader=fake_loader)
        mode, _, cands = ed._detect_completion('{Scan/Det/CH00}["CH00"].mean("')
        assert mode == 'M4'
        assert 'scan_axis' in cands
        assert loader_calls == ['Scan/Det/CH00']

    def test_loader_result_cached(self, qapp):
        """Loader is only called once; subsequent calls use the cached dataset."""
        ds = _ds({'CH00': ['t']})
        call_count = [0]

        def counting_loader(name):
            call_count[0] += 1
            return ds

        ed = _editor({'path/ds': None}, h5_loader=counting_loader)
        ed._detect_completion('{path/ds}["CH00"].mean("')
        ed._detect_completion('{path/ds}["CH00"].mean("t')
        assert call_count[0] == 1   # loaded once, then cached

    def test_prefix_filters_dims(self, qapp):
        ds = _ds({'v': ['scan_axis', 'det_axis', 'time']})
        ed = _editor({'ds': ds})
        mode, _, cands = ed._detect_completion('{ds}.sum("scan')
        assert mode == 'M4'
        assert 'scan_axis' in cands
        assert 'det_axis' not in cands
        assert 'time' not in cands

    def test_consumed_dims_excluded(self, qapp):
        """A dim used by an earlier .mean() in the chain must not reappear."""
        ds = _ds({'v': ['x', 'y', 'z']})
        ed = _editor({'ds': ds})
        mode, _, cands = ed._detect_completion('{ds}.mean("x").mean("')
        assert mode == 'M4'
        assert 'x' not in cands
        assert 'y' in cands and 'z' in cands

    def test_works_after_bracket_indexing(self, qapp):
        """Dims should still be proposed after {name}["var"].mean("."""
        ds = _ds({'CH00': ['row', 'col']})
        ed = _editor({'p/ds': ds})
        mode, _, cands = ed._detect_completion('{p/ds}["CH00"].mean("')
        assert mode == 'M4'
        assert 'row' in cands and 'col' in cands

    def test_p3_fallback_bare_dataset_ref(self, qapp):
        """Bare {name}.mean(" (no ["var"]) also resolves dims via P3."""
        ds = _ds({'CH00': ['alpha', 'beta']})
        ed = _editor({'ds': ds})
        mode, _, cands = ed._detect_completion('{ds}.mean("')
        assert mode == 'M4'
        assert 'alpha' in cands and 'beta' in cands
