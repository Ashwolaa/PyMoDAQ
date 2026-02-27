"""Shared formatting and result-coercion helpers for the DataMixer GUI.

This module centralises:

* ``_wrap_result``      — coerce any eval() return value to a DataWithAxes
* ``_format_xr_html``  — HTML summary of an xr.Dataset
* ``_format_dwa_html`` — HTML summary of a DataWithAxes
"""
import html as _html

import numpy as np

from pymodaq_data.data import DataWithAxes, DataSource


# ── Result coercion ───────────────────────────────────────────────────────────

def _wrap_result(result, name: str) -> DataWithAxes:
    """Coerce any eval() return value to a named DataWithAxes.

    Handled types
    -------------
    xr.Dataset  (1 var)  → extract DataArray, convert via DataWithAxes.from_xarray
    xr.Dataset  (N vars) → from_xarray with attrs dropped
    xr.DataArray         → to_dataset(name=var_name), from_xarray
    DataWithAxes         → rename and return
    np.ndarray           → wrap as single-array DataWithAxes
    tuple/list of arrays → each element as a separate .data entry
    scalar               → wrap as 1-element array
    """
    try:
        import xarray as xr
        if isinstance(result, xr.Dataset):
            if len(result.data_vars) == 1:
                var_name = list(result.data_vars)[0]
                da = result[var_name]
                dwa = DataWithAxes.from_xarray(da.to_dataset(name=var_name))
            else:
                dwa = DataWithAxes.from_xarray(result.drop_attrs())
            dwa.name = name
            return dwa
        if isinstance(result, xr.DataArray):
            var_name = result.name or name
            dwa = DataWithAxes.from_xarray(result.to_dataset(name=var_name))
            dwa.name = name
            return dwa
    except ImportError:
        pass
    if isinstance(result, DataWithAxes):
        result.name = name
        return result
    if isinstance(result, np.ndarray):
        return DataWithAxes(name, source=DataSource['calculated'], data=[result])
    if isinstance(result, (tuple, list)) and all(isinstance(r, np.ndarray) for r in result):
        return DataWithAxes(name, source=DataSource['calculated'], data=list(result))
    if isinstance(result, (int, float, np.integer, np.floating, np.bool_)):
        return DataWithAxes(name, source=DataSource['calculated'],
                            data=[np.array([float(result)])])
    raise TypeError(
        f'Formula returned {type(result).__name__!r} — expected a DataWithAxes, '
        f'xarray Dataset/DataArray, numpy array, tuple of arrays, or scalar.')


# ── Rich output formatting ────────────────────────────────────────────────────

def _format_xr_html(ds, result_name: str) -> str:
    """HTML summary of an xr.Dataset — similar to IPython's xarray display."""
    _C = 'color:#555'
    _B = 'color:#1a3c6b'

    rows = []

    # Dimensions
    dims_parts = [f'<b>{d}</b>({n})' for d, n in ds.sizes.items()]
    rows.append(f'<span style="{_C}">Dimensions:</span>  ' + ' &nbsp;·&nbsp; '.join(dims_parts))

    # Coordinates
    for cname, cvar in ds.coords.items():
        units = cvar.attrs.get('units', '')
        units_str = f'  units=<b>{units!r}</b>' if units else ''
        data = cvar.values
        if data.ndim == 1 and data.size > 0:
            rng = f'  [<b>{data[0]:.4g}</b> … <b>{data[-1]:.4g}</b>]'
        elif data.ndim > 1:
            rng = f'  shape={data.shape}'
        else:
            rng = ''
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">*</span> '
            f'<b>{_html.escape(cname)}</b> '
            f'({", ".join(_html.escape(str(d)) for d in cvar.dims)}) '
            f'{cvar.dtype}{rng}{units_str}')

    # Data variables
    for vname, var in ds.data_vars.items():
        vals = var.values
        dims_str = ', '.join(_html.escape(str(d)) for d in var.dims)
        if vals.size > 0:
            stats = (f'  min=<b>{float(vals.min()):.4g}</b>'
                     f'  max=<b>{float(vals.max()):.4g}</b>'
                     f'  mean=<b>{float(vals.mean()):.4g}</b>')
        else:
            stats = '  (empty)'
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">var</span> '
            f'<b>{_html.escape(vname)}</b> '
            f'({dims_str}) {var.dtype}{stats}')

    ref = (f'{{<b>{_html.escape(result_name)}</b>}}'
           f'[&quot;<b>{_html.escape(result_name)}</b>&quot;]')
    header = (f'<span style="color:#1a6b1a"><b>xr.Dataset</b></span>'
              f' — stored in context, reference as {ref}')
    body = '<br>'.join('&nbsp;&nbsp;' + r for r in rows)
    return header + '<br>' + body


def _format_xr_lazy_html(ds, result_name: str) -> str:
    """HTML summary for a lazy (dask-backed) xr.Dataset.

    Unlike ``_format_xr_html``, this never calls ``.values`` on data variables
    so it is safe to call on very large dask-backed arrays.  Coordinates
    (small axis arrays) are still materialised for range display.
    """
    _C = 'color:#555'

    rows = []

    # Dimensions
    dims_parts = [f'<b>{d}</b>({n})' for d, n in ds.sizes.items()]
    rows.append(f'<span style="{_C}">Dimensions:</span>  ' + ' &nbsp;·&nbsp; '.join(dims_parts))

    # Coordinates — usually small axis arrays, safe to materialise
    for cname, cvar in ds.coords.items():
        units = cvar.attrs.get('units', '')
        units_str = f'  units=<b>{units!r}</b>' if units else ''
        try:
            data = cvar.values
            if data.ndim == 1 and data.size > 0:
                rng = f'  [<b>{data[0]:.4g}</b> … <b>{data[-1]:.4g}</b>]'
            else:
                rng = f'  shape={data.shape}'
        except Exception:
            rng = ''
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">*</span> '
            f'<b>{_html.escape(cname)}</b> '
            f'({", ".join(_html.escape(str(d)) for d in cvar.dims)}) '
            f'{cvar.dtype}{rng}{units_str}')

    # Data variables — dtype + chunk info only, no .values call
    for vname, var in ds.data_vars.items():
        dims_str = ', '.join(_html.escape(str(d)) for d in var.dims)
        chunks_info = ''
        if hasattr(var, 'chunks') and var.chunks:
            chunk_sizes = [f'<b>{d}</b>:{c[0]}' for d, c in zip(var.dims, var.chunks)]
            chunks_info = '  chunks=(' + ', '.join(chunk_sizes) + ')'
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">var</span> '
            f'<b>{_html.escape(vname)}</b> '
            f'({dims_str}) {var.dtype}{chunks_info}'
            f'  <span style="color:#1a5cb5"><i>[lazy — not yet computed]</i></span>')

    ref = (f'{{<b>{_html.escape(result_name)}</b>}}'
           f'[&quot;<b>{_html.escape(result_name)}</b>&quot;]')
    header = (f'<span style="color:#1a5cb5"><b>xr.Dataset [lazy]</b></span>'
              f' — stored in context, reference as {ref}')
    body = '<br>'.join('&nbsp;&nbsp;' + r for r in rows)
    return header + '<br>' + body


def _format_dwa_html(dwa: DataWithAxes) -> str:
    """HTML summary of a DataWithAxes — shape, axes, data stats."""
    _C = 'color:#555'

    rows = []
    rows.append(
        f'shape=<b>{dwa.shape}</b>'
        f'  nav_indexes=<b>{dwa.nav_indexes}</b>'
        f'  distribution=<b>{dwa.distribution.name}</b>'
    )

    for ax in sorted(dwa.axes, key=lambda a: a.index):
        ax_data = ax.get_data()
        units_str = f'  units=<b>{ax.units!r}</b>' if ax.units else ''
        if ax_data is not None and ax_data.size > 0:
            rng = f'  [<b>{ax_data[0]:.4g}</b> … <b>{ax_data[-1]:.4g}</b>]'
        else:
            rng = ' (linspace)'
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">axis</span> '
            f'<b>{_html.escape(repr(ax.label))}</b>'
            f'  idx={ax.index}  size={ax.size}'
            f'{rng}{units_str}')

    for i, (arr, label) in enumerate(zip(dwa.data, dwa.labels)):
        if arr.size > 0:
            stats = (f'min=<b>{float(arr.min()):.4g}</b>'
                     f'  max=<b>{float(arr.max()):.4g}</b>'
                     f'  mean=<b>{float(arr.mean()):.4g}</b>')
        else:
            stats = '(empty)'
        rows.append(
            f'&nbsp;&nbsp;<span style="{_C}">data[{i}]</span>'
            f' <b>{_html.escape(label)}</b>'
            f' {arr.dtype}  {stats}')

    header = '<span style="color:#1a2f6b"><b>DataWithAxes</b></span> — sent to viewer'
    body = '<br>'.join('&nbsp;&nbsp;' + r for r in rows)
    return header + '<br>' + body
