# xarray Integration for DataMixerModelH5 — Progress

## Status: IMPLEMENTED & TESTED

All formula evaluation paths pass against the real H5 file
(`Scan_20260222_09_13_10.h5`).

---

## What was done

### Files modified

| File | Change |
|------|--------|
| `packages/pymodaq/src/pymodaq/extensions/data_mixer/parser.py` | Added `replace_names_in_formula_xr` |
| `packages/pymodaq/src/pymodaq/extensions/data_mixer/models/h5_model.py` | xarray eval path in `compute()`, new `_compute_formula_xr`, updated `_wrap_result` |

---

### `parser.py` — new function

```python
def replace_names_in_formula_xr(formula, ctx_var='_xr'):
```

Sister to `replace_names_in_formula`. Maps `{some/name}` →
`_xr["some/name"]` instead of `dte.get_data_from_full_name("some/name")`.
The `{` and `}` delimiters are unchanged so the autocomplete system works
without modification.

---

### `h5_model.py` — three changes

**1. `_wrap_result` — xarray handling added first**

Result types handled in order:
- `xr.Dataset` with 1 data var → extract that var as DataArray, convert to DWA
  (single-var extraction avoids a Dataset-level dim-reordering bug in xarray
  arithmetic that breaks `from_xarray`'s axis reconstruction)
- `xr.Dataset` with multiple vars → `drop_attrs()` then `from_xarray`
- `xr.DataArray` → `to_dataset(name=var_name)` then `from_xarray`
- `DataWithAxes`, `np.ndarray`, tuple of arrays, scalar — unchanged

**2. `_compute_formula_xr` — new method**

```python
def _compute_formula_xr(self, formula, xr_ctx, xr, name):
    formula_to_eval, _ = replace_names_in_formula_xr(formula)
    result = eval(formula_to_eval, {'np': np, 'xr': xr, '_xr': xr_ctx})
    dwa = _wrap_result(result, name)
    # Store raw xarray result in xr_ctx (no DWA round-trip):
    if isinstance(result, xr.DataArray):
        xr_ctx[name] = result.to_dataset(name=name)  # var named by output name
    elif isinstance(result, xr.Dataset):
        xr_ctx[name] = result
    else:
        try:
            ds = dwa.to_xarray()
            xr_ctx[name] = ds.assign_attrs(...)  # strip pymodaq_ attrs
        except Exception:
            pass
    return dwa
```

Key design decisions:
- `xr_ctx` is updated inside `_compute_formula_xr` (not in `compute()`) so the
  raw xarray object is stored directly — no DWA→xarray round-trip. Round-tripping
  failed because `from_xarray` on a result DWA can trigger spread/axis errors.
- DataArray results are stored under `xr_ctx[name]` with the data variable named
  `name`. So `{result_name}["result_name"]` is the consistent cross-reference
  syntax, regardless of original channel label.

**3. `compute()` — xarray path primary, DWA fallback**

```python
def compute(self):
    try:
        import xarray as xr
        _xarray_available = True
    except ImportError:
        _xarray_available = False

    loader = DataLoader(self._h5saver_low)
    dte_from_h5 = loader.load_all('/')

    if _xarray_available:
        xr_ctx = {}
        for full_name in dte_from_h5.get_full_names():
            xr_ctx[full_name] = dte_from_h5.get_data_from_full_name(full_name).to_xarray()
        for name, formula in formulae:
            dwa = self._compute_formula_xr(formula, xr_ctx, xr, name)
            ...
    else:
        # fallback: original FormulaDTE / DataWithAxes path
        ...
```

---

## Formula syntax

`{name}` in formulas now resolves to an `xr.Dataset`. The user accesses the
specific channel via `["channel_label"]` to get an `xr.DataArray`. Both `np`
and `xr` are available in the eval scope.

### H5 data access

H5 datasets are keyed by their full name (`origin/DWA_name`):

```
# Full name from H5: 'test/Mock2D_0', data var 'CH00'
{test/Mock2D_0}["CH00"]              # xr.DataArray (25, 200, 100)
{test/Mock2D_0}["CH00"] * 2          # element-wise scalar
{test/Mock2D_0}["CH00"].mean("time") # reduce over nav dim → (200, 100)
{test/Mock2D_0}["CH00"].isel(time=5) # slice timeframe 5 → (200, 100)
{test/Mock2D_0}["CH00"] - {test/Mock2D_1}["CH00"]  # auto-aligns on coords
np.sqrt({test/Mock2D_0}["CH00"])     # numpy ufunc
{test/Mock2D_0} * 3                  # Dataset arithmetic (single-var case)
```

### Cross-referencing intermediate results

Named formula outputs are available to later lines via `{name}["name"]`:

```
a = {test/Mock2D_0}["CH00"].mean("time")   # stored as xr_ctx["a"]["a"]
b = {a}["a"] + 1                            # references 'a', adds 1
c = {a}["a"] - {test/Mock2D_1}["CH00"].mean("time")  # mixed reference
```

---

## Known issues / quirks

### DataSizeWarning on H5 load

The spread data loaded from the H5 file (`AxesManagerSpread` with nav_indexes)
may trigger `DataSizeWarning` and `DataIndexWarning` during `loader.load_all()`
in some configurations. These come from the H5 reader, not from the xarray
formula path, and do not affect correctness of the formula evaluation.

### Spread distribution not propagated to formula results

Formula results (DataArray or Dataset) are always reconstructed as
`distribution='uniform'` with `nav_indexes=()`. The original nav/spread
structure is not propagated because:
1. xarray arithmetic may reorder Dataset-level dims (breaking `from_xarray`)
2. Formula results are semantically new quantities — they may have fewer dims
   (e.g. after `.mean("time")`) so the original nav structure no longer applies.

For the viewer this means: a formula producing a (25, 200, 100) result will be
treated as 3D uniform data without a designated navigation axis. The data is
correct; only the viewer's dimension-navigation designation is lost. This is
acceptable for the formula-computation use case and simplifies correctness.

### `from_xarray` dim-order bug (tracked for future fix)

xarray Dataset arithmetic (`ds * 3`, `ds1 + ds2`, etc.) may reorder
Dataset-level dims relative to the individual data-variable dims. `from_xarray`
uses `list(ds.dims)` for axis-index mapping, which picks up this reordered
view. The workaround (extract DataArray from single-var Datasets) is in place.
A proper fix would be in `DataWithAxes.from_xarray`: use the dim order from the
first data variable's `.dims` rather than `ds.dims`.

---

## formula_debugger.py (updated)

`examples/formula_debugger.py` is updated to use the xarray path and shows rich
output after each formula so it's clear what is stored and what the viewer gets.

**What's stored — two objects per result:**

| Object | Where | What it is | How to reference |
|--------|-------|------------|-----------------|
| `xr.Dataset` | `xr_ctx[name]` | Dataset with one data var named `name`, labeled dims, coords with units | `{name}["name"]` in the next formula line |
| `DataWithAxes` | returned to viewer | shape, nav_indexes, axes reconstructed from Dataset dims/coords | plotted by ViewerDispatcher |

**Output per formula** (shown in the GUI output panel):

```
[mean_t]  {test/Mock2D_0}["CH00"].mean("time")
  eval: _xr["test/Mock2D_0"]["CH00"].mean("time")

  xr.Dataset — stored in context, reference as {mean_t}["mean_t"]
    Dimensions:  the y axis(200) · the x axis(100)
    * the y axis  (the y axis) float64  [0.0 … 199.0]
    * the x axis  (the x axis) float64  [0.0 … 99.0]
    var mean_t  (the y axis, the x axis) float64  min=-0.04  max=1.01  mean=0.50

  DataWithAxes — sent to viewer
    shape=(200, 100)  nav_indexes=()  distribution=uniform
    axis 'the y axis'  idx=0  size=200  [0.0 … 199.0]
    axis 'the x axis'  idx=1  size=100  [0.0 … 99.0]
    data[0] mean_t  float64  min=-0.04  max=1.01  mean=0.50
```

## Verification checklist

- [x] `replace_names_in_formula_xr` translates `{a/b}` → `_xr["a/b"]`
- [x] H5 full names correctly populate `xr_ctx` via `to_xarray()`
- [x] DataArray formulas: `* 2`, `.mean("time")`, `.isel(time=5)` → correct DWA shape
- [x] Two-channel subtraction auto-aligns on shared coords
- [x] Dataset arithmetic (`{ds} * 3`) single-var case → correct DWA
- [x] `np.sqrt(...)` and other ufuncs work
- [x] Cross-referencing: `{a}["a"]` accesses intermediate result by output name
- [x] Cross-reference chain: `{b}["b"]` uses `{a}` result from previous line
- [x] Scalar formula (`float(...)`) → 0D DWA
- [x] xarray not installed → falls back to original `FormulaDTE` / DWA path
