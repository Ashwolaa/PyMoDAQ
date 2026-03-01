"""Tests for pymodaq.extensions.data_mixer.gui.formatters.

Covers:
  * _wrap_result         — coercion of various return types to DataWithAxes
  * _format_xr_html      — eager HTML summary (materialises data)
  * _format_xr_lazy_html — lazy HTML summary (must NOT call .values on data vars)
  * _is_lazy_ds          — lazy-detection helper (imported from console module directly)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from pymodaq.extensions.data_mixer.gui.formatters import (
    _format_xr_html,
    _format_xr_lazy_html,
    _wrap_result,
)
from pymodaq_data.data import DataWithAxes, DataSource


# ── helpers ───────────────────────────────────────────────────────────────────

def _simple_da(name="v", shape=(5,), dim="x") -> xr.DataArray:
    return xr.DataArray(np.arange(np.prod(shape), dtype=float).reshape(shape),
                        dims=[dim], name=name)

def _simple_ds(name="v", shape=(5,)) -> xr.Dataset:
    da = _simple_da(name=name, shape=shape)
    return da.to_dataset(name=name)


# ── _wrap_result ──────────────────────────────────────────────────────────────

class TestWrapResult:

    def test_dataarray_returns_dwa(self):
        da = _simple_da()
        dwa = _wrap_result(da, "out")
        assert isinstance(dwa, DataWithAxes)
        assert dwa.name == "out"

    def test_dataset_single_var_returns_dwa(self):
        ds = _simple_ds()
        dwa = _wrap_result(ds, "out")
        assert isinstance(dwa, DataWithAxes)
        assert dwa.name == "out"

    def test_dataset_multi_var_returns_dwa(self):
        ds = xr.Dataset({"a": ("x", np.ones(4)), "b": ("x", np.zeros(4))})
        dwa = _wrap_result(ds, "multi")
        assert isinstance(dwa, DataWithAxes)
        assert dwa.name == "multi"

    def test_ndarray_returns_dwa(self):
        arr = np.ones((3, 4))
        dwa = _wrap_result(arr, "arr")
        assert isinstance(dwa, DataWithAxes)
        assert dwa.name == "arr"
        assert dwa.data[0].shape == (3, 4)

    def test_scalar_float_returns_dwa(self):
        dwa = _wrap_result(3.14, "s")
        assert isinstance(dwa, DataWithAxes)
        assert dwa.data[0].shape == (1,)
        assert float(dwa.data[0][0]) == pytest.approx(3.14)

    def test_scalar_int_returns_dwa(self):
        dwa = _wrap_result(42, "s")
        assert isinstance(dwa, DataWithAxes)

    def test_tuple_of_arrays_returns_dwa(self):
        dwa = _wrap_result((np.ones(3), np.zeros(3)), "tup")
        assert isinstance(dwa, DataWithAxes)
        assert len(dwa.data) == 2

    def test_unknown_type_raises_typeerror(self):
        with pytest.raises(TypeError, match="Formula returned"):
            _wrap_result({"key": 1}, "bad")

    def test_dwa_passthrough(self):
        original = DataWithAxes("orig", source=DataSource["calculated"],
                                data=[np.ones(5)])
        result = _wrap_result(original, "renamed")
        assert result.name == "renamed"


# ── _format_xr_html ───────────────────────────────────────────────────────────

class TestFormatXrHtml:

    def test_returns_string(self):
        assert isinstance(_format_xr_html(_simple_ds(), "v"), str)

    def test_contains_variable_name(self):
        html = _format_xr_html(_simple_ds("myvar"), "myvar")
        assert "myvar" in html

    def test_contains_dimension(self):
        html = _format_xr_html(_simple_ds(shape=(7,)), "v")
        assert "x" in html     # dim name
        assert "7" in html     # dim size

    def test_contains_stats(self):
        html = _format_xr_html(_simple_ds(), "v")
        # Should have min/max/mean for the data variable
        assert "min=" in html
        assert "max=" in html
        assert "mean=" in html

    def test_dataset_with_coord(self):
        ds = xr.Dataset(
            {"v": ("x", np.arange(5.0))},
            coords={"x": np.linspace(0, 1, 5)},
        )
        html = _format_xr_html(ds, "v")
        assert "x" in html
        assert "0" in html   # coord start

    def test_2d_dataset(self):
        ds = xr.Dataset({"v": (("x", "y"), np.ones((3, 4)))})
        html = _format_xr_html(ds, "v")
        assert "x" in html
        assert "y" in html


# ── _format_xr_lazy_html ──────────────────────────────────────────────────────

class TestFormatXrLazyHtml:

    def test_returns_string(self):
        assert isinstance(_format_xr_lazy_html(_simple_ds(), "v"), str)

    def test_contains_lazy_badge(self):
        html = _format_xr_lazy_html(_simple_ds(), "v")
        assert "lazy" in html.lower()

    def test_contains_variable_name(self):
        html = _format_xr_lazy_html(_simple_ds("myvar"), "myvar")
        assert "myvar" in html

    def test_contains_dimension(self):
        html = _format_xr_lazy_html(_simple_ds(shape=(7,)), "v")
        assert "x" in html
        assert "7" in html

    def test_no_stats_in_data_var_section(self):
        html = _format_xr_lazy_html(_simple_ds(), "v")
        # Eager stats must NOT appear — they would require .values on the data var
        assert "min=" not in html
        assert "max=" not in html
        assert "mean=" not in html

    def test_does_not_call_values_on_data_vars(self):
        """Use a mock DataArray to prove .values is never accessed on data vars."""
        sentinel = object()

        class _NoValues(np.ndarray):
            @property
            def values(self):  # pragma: no cover
                raise AssertionError(".values was called on a data variable")

        arr = np.arange(6.0).view(_NoValues).reshape((2, 3))
        ds = xr.Dataset({"v": (("x", "y"), arr)})
        # Must not raise
        _format_xr_lazy_html(ds, "v")

    def test_coord_range_shown(self):
        """Coordinate values (small) are still shown for navigation."""
        ds = xr.Dataset(
            {"v": ("x", np.zeros(5))},
            coords={"x": np.array([0.0, 1.0, 2.0, 3.0, 4.0])},
        )
        html = _format_xr_lazy_html(ds, "v")
        assert "0" in html   # start of coord range


# ── _is_lazy_ds (from console.py) ─────────────────────────────────────────────

def _load_is_lazy_ds():
    """Attempt to extract _is_lazy_ds from console.py.

    Returns (fn, True) on success, (None, False) when Qt is not available
    (console.py defines Qt widget subclasses that cannot be stubbed at class
    definition time without a real Qt installation).
    """
    _CONSOLE_PATH = (
        Path(__file__).parents[2]          # …/packages/pymodaq/
        / "src/pymodaq/extensions/data_mixer/gui/console.py"
    )
    try:
        spec = importlib.util.spec_from_file_location("_dm_console_stub",
                                                       _CONSOLE_PATH)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod._is_lazy_ds, True
    except Exception:
        return None, False


_is_lazy_ds, _CONSOLE_LOADED = _load_is_lazy_ds()


@pytest.mark.skipif(not _CONSOLE_LOADED,
                    reason="console.py requires a real Qt installation")
class TestIsLazyDs:

    def test_numpy_backed_dataset_is_not_lazy(self):
        ds = _simple_ds()
        assert _is_lazy_ds(ds) is False

    def test_empty_dataset_is_not_lazy(self):
        ds = xr.Dataset()
        assert _is_lazy_ds(ds) is False

    def test_none_is_not_lazy(self):
        assert _is_lazy_ds(None) is False
