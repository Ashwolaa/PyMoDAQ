# xarray Integration Plan for PyMoDAQ Data Classes

## Context

PyMoDAQ's `DataWithAxes` is a rich N-dimensional data container with labeled axes, pint units,
navigation/signal dimension separation, and optional error arrays. Adding bidirectional conversion
to/from xarray enables the xarray ecosystem (groupby, rolling, multi-dim interp, dask, hvplot,
etc.) without permanently migrating away from PyMoDAQ.

**DataTree** (stable in xarray >= 2024.10.0) is used for `DataToExport` because it maps naturally
to PyMoDAQ's hierarchy: root node = `DataToExport`, child nodes = individual `DataWithAxes` items.
This is cleaner than a plain dict and supports NetCDF4/Zarr I/O out of the box.

**Dict in attrs:** xarray attrs accept dicts in memory but break NetCDF4/Zarr serialization (attrs
must be scalars or 1D arrays). The DataTree hierarchy itself provides the nesting — no
dict-in-attrs needed. All attr values are kept as scalars or flat lists.

---

## Conceptual Mapping

| PyMoDAQ | xarray |
|---|---|
| `DataWithAxes` (multiple arrays, same shape) | `xr.Dataset` |
| `self.data[i]` + `self.labels[i]` | data variable (name = label, value = array) |
| `Axis(label, units, data, index=i)` | dimension `i` with named coordinate + attrs |
| `nav_indexes`, `source`, `units`, `origin`, `name` | `Dataset.attrs` with `pymodaq_` prefix |
| `errors[i]` | data variable `f'{label}_error'` |
| `DataToExport` (list of DWAs) | `xr.DataTree` (root + one child node per DWA) |

---

## Files to Modify

1. `packages/pymodaq_data/src/pymodaq_data/data.py` — add methods to `DataWithAxes` and `DataToExport`
2. `packages/pymodaq_data/pyproject.toml` — add `xarray` as optional dependency
3. `packages/pymodaq_data/tests/data_test.py` — add `TestXarrayConversion` test class

---

## Implementation

### 1. `DataWithAxes.to_xarray() -> xr.Dataset`

Insert just before the `DataRaw` class definition (after line 2853 in `data.py`).

**Algorithm:**

1. **Build dimension names** — one per shape dimension `i`:
   - `axes_at_i = self.get_axis_from_index(i)` → use `axes_at_i[0].label` or fall back to `f'dim_{i}'`
   - Deduplicate by appending `_N` suffix when the same label appears on multiple dimensions

2. **Build coordinates** — for each `Axis` in `self.axes`:
   - Coordinate name = `axis.label` if non-empty, else the dim name
   - For spread data with `spread_order > 0`: coord name = `f'{label}_{axis.spread_order}'`
   - Coordinate attrs: `{'units': axis.units, 'pymodaq_label': axis.label}`, plus `'spread_order'` for spread axes

3. **Build data variables** — for each `(array, label)` pair in `zip(self.data, self.labels)`:
   - Variable named `label` (or `f'data_{i}'` if label is empty)

4. **Errors** — if `self.errors is not None`: add `f'{label}_error'` data variables; list their names in `attrs['pymodaq_error_vars']`

5. **Dataset attrs** — all scalars/flat lists (serialization-safe):
   - `pymodaq_name`, `pymodaq_origin`
   - `pymodaq_source` (`'raw'` or `'calculated'`)
   - `pymodaq_distribution` (`'uniform'` or `'spread'`)
   - `pymodaq_units`
   - `pymodaq_nav_indexes` (list of ints)
   - `pymodaq_labels` (list of str)
   - `pymodaq_error_vars` (list of str, only if errors present)

---

### 2. `DataWithAxes.from_xarray(cls, ds) -> DataWithAxes` — classmethod

Insert immediately after `to_xarray()`.

**Algorithm:**

1. Accept `xr.Dataset` or `xr.DataArray`; convert DataArray → Dataset via `.to_dataset(name=da.name or 'data')`
2. Read `pymodaq_*` attrs; fall back gracefully to defaults for generic xarray Datasets
3. Separate error data_vars (named in `pymodaq_error_vars`) from regular data_vars
4. Reconstruct `Axis` objects from `ds.dims` and `ds.coords`:
   - For each dim index `i`, dim name = `list(ds.dims)[i]`
   - If coord exists: `Axis(label=coord.attrs.get('pymodaq_label', dim_name), units=coord.attrs.get('units', ''), data=coord.values, index=i)`
   - For spread: also reconstruct secondary coords via `spread_order` in coord attrs
   - If no coord found: `Axis(label=dim_name, index=i, size=ds.dims[dim_name])`
5. Return:
   ```python
   DataWithAxes(
       name=name, source=DataSource[source_str],
       distribution=DataDistribution[distribution_str],
       data=data_arrays, labels=labels, units=units,
       axes=axes, nav_indexes=nav_indexes, origin=origin, errors=errors,
   )
   ```

> Always returns `DataWithAxes` (base class, not a subclass) since `source` is set explicitly.

---

### 3. `DataToExport.to_xarray() -> xr.DataTree`

Insert near the end of `DataToExport` class (before `if __name__ == '__main__':`).

```python
def to_xarray(self):
    children = {dwa.name: xr.DataTree(dataset=dwa.to_xarray()) for dwa in self}
    return xr.DataTree(children=children, attrs={'pymodaq_name': self.name})
```

---

### 4. `DataToExport.from_xarray(cls, dt, name=None) -> DataToExport` — classmethod

- Accept `xr.DataTree` (or `Dict[str, xr.Dataset]` for flexibility)
- For DataTree: iterate `dt.children` → each child's `.dataset` → `DataWithAxes.from_xarray(child.dataset)`
- For dict: `DataWithAxes.from_xarray(ds)` for each value
- `name = name or dt.attrs.get('pymodaq_name', 'from_xarray')`
- Return `DataToExport(name=name, data=data_list)`

---

### 5. `pyproject.toml` — optional dependency

```toml
[project.optional-dependencies]
xarray = ["xarray>=2024.10"]   # DataTree requires 2024.10+
```

Both `to_xarray()` and `from_xarray()` import xarray lazily inside the method body and raise a
clear `ImportError` if the package is missing:

```
xarray is required. Install it with: pip install 'pymodaq_data[xarray]'
```

---

## Tests (`tests/data_test.py`)

Add class `TestXarrayConversion` with `xr = pytest.importorskip('xarray')` at the top so the
whole class is skipped gracefully if xarray is not installed.

| Test | What it checks |
|---|---|
| `test_to_xarray_dims_coords` | 1D DataRaw: dim name matches axis label, coord data matches `axis.get_data()`, coord has `units` attr |
| `test_to_xarray_data_vars` | Multi-label DataRaw: each label → data_var, array values match |
| `test_to_xarray_attrs` | `pymodaq_name`, `pymodaq_nav_indexes`, `pymodaq_source`, `pymodaq_units` present in `Dataset.attrs` |
| `test_round_trip_1d` | `from_xarray(to_xarray(dwa))`: array values, axis label/units/data, name all preserved |
| `test_round_trip_2d_nav` | 2D DataRaw with `nav_indexes=(0,)`: nav_indexes survive the round-trip |
| `test_round_trip_errors` | DataRaw with errors: error arrays preserved, not duplicated in data_vars |
| `test_from_dataarray` | `xr.DataArray` input to `from_xarray()` works without error |
| `test_dte_to_datatree` | `DataToExport.to_xarray()` returns `xr.DataTree` with correct number of children |
| `test_dte_round_trip` | `DataToExport.from_xarray(dte.to_xarray())`: names and shapes match the original |

---

## Verification

```bash
cd packages/pymodaq_data
pip install "xarray>=2024.10"
python -m pytest tests/data_test.py::TestXarrayConversion -v
```

---

## Non-goals / Future work

- **pint-xarray**: Units could be attached to DataArray/Dataset coordinates using `pint-xarray`
  for proper unit-aware operations. Left as a future enhancement to avoid an additional dependency.
- **Full `DataToExport` merge**: When all DWAs share the same coordinate system, a single merged
  Dataset (rather than a DataTree) could be returned. Not implemented now; the tree approach is
  always valid.
- **Replacing `DataWithAxes` with xarray**: The conceptual fit is strong but migration cost
  (3,500-line `data.py`, entire plugin ecosystem) is too high for now. These conversion methods
  validate the mapping in practice before committing to a deeper integration.
