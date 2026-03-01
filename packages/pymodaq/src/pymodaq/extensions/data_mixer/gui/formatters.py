"""Shared formatting and result-coercion helpers for the DataMixer GUI.

This module centralises:

* ``_collect_h5_names_and_info`` — walk an H5 file and return names + metadata
* ``_wrap_result``               — coerce any eval() return value to a DataWithAxes
* ``_format_xr_html``            — HTML summary of an xr.Dataset
* ``_format_xr_lazy_html``       — lazy HTML summary (no .values call on data vars)
"""
import html as _html

import numpy as np

from pymodaq_data.data import DataWithAxes, DataSource
from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))


# ── H5 name + lightweight info collection (no data loading) ──────────────────

def _collect_h5_names_and_info(h5saver) -> tuple:
    """Single-pass walk: return ``(names, info)`` without loading any array data.

    ``names`` is a list of rel_path strings.
    ``info``  is a ``{rel_path: str}`` dict with ``"dtype shape"`` metadata read
    directly from the HDF5 node's ``shape`` / ``dtype`` attributes — no array
    data is transferred from disk.

    This lets the variable browser populate its Info column immediately after
    a file is loaded, without waiting for the user to click each row.
    """
    from pymodaq_data.h5modules.backends import GROUP

    try:
        h5saver.get_node('/RawData')
        base = '/RawData'
    except Exception:
        base = '/'

    names: list = []
    info: dict = {}
    seen_parents: set = set()

    for node in h5saver.walk_nodes(base):
        if isinstance(node, GROUP):
            continue
        try:
            dt = node.attrs['data_type']
            if 'data' not in str(dt):
                continue
        except Exception:
            continue

        try:
            parent_path = node.parent_node.path
        except Exception as exc:
            logger.debug(f'Cannot get parent path for {node.path!r}: {exc}')
            continue

        if parent_path in seen_parents:
            continue
        seen_parents.add(parent_path)

        rel = parent_path[len(base):].lstrip('/')
        if not rel:
            rel = node.path[len(base):].lstrip('/').split('/')[0] or 'data'

        names.append(rel)

        # Shape and dtype from node metadata — no data read.
        # PyMoDAQ backends store these as HDF5 attributes ('shape', 'dtype'),
        # so we try attrs first before falling back to native properties.
        try:
            node_attrs = getattr(node, 'attrs', {})
            shape = node_attrs.get('shape') if hasattr(node_attrs, 'get') else None
            if shape is None:
                shape = getattr(node, 'shape', None)
            dtype = node_attrs.get('dtype') if hasattr(node_attrs, 'get') else None
            if dtype is None:
                try:
                    dtype = str(node.dtype)
                except AttributeError:
                    dtype = str(getattr(getattr(node, 'atom', None), 'dtype', '?'))
            info[rel] = f'{dtype} {shape}'
        except Exception as exc:
            logger.warning(f'Cannot read metadata for {rel!r}: {exc}')
            info[rel] = '?'

    return names, info


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

def _format_xr_html(ds, result_name: str, colors: dict | None = None) -> str:
    """HTML summary of an xr.Dataset — similar to IPython's xarray display.

    Parameters
    ----------
    colors:
        Optional dict with keys ``'dim'`` (secondary label colour),
        ``'type'`` (dtype/coord label colour) and ``'dataset'`` (header
        colour).  When omitted, defaults that look reasonable in both light
        and dark themes are used.
    """
    _c = colors or {}
    _C = f'color:{_c.get("dim", "#888")}'
    _B = f'color:{_c.get("type", "#1a3c6b")}'
    _DS_COLOR = _c.get('dataset', '#1a6b1a')

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
    header = (f'<span style="color:{_DS_COLOR}"><b>xr.Dataset</b></span>'
              f' — stored in context, reference as {ref}')
    body = '<br>'.join('&nbsp;&nbsp;' + r for r in rows)
    return header + '<br>' + body


def _format_xr_lazy_html(ds, result_name: str, colors: dict | None = None) -> str:
    """HTML summary for a lazy (dask-backed) xr.Dataset.

    Unlike ``_format_xr_html``, this never calls ``.values`` on data variables
    so it is safe to call on very large dask-backed arrays.  Coordinates
    (small axis arrays) are still materialised for range display.

    Parameters
    ----------
    colors:
        Same palette-derived dict accepted by :func:`_format_xr_html`.
    """
    _c = colors or {}
    _C = f'color:{_c.get("dim", "#888")}'
    _LAZY_COLOR = _c.get('lazy', '#1a5cb5')

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
            f'  <span style="color:{_LAZY_COLOR}"><i>[lazy — not yet computed]</i></span>')

    ref = (f'{{<b>{_html.escape(result_name)}</b>}}'
           f'[&quot;<b>{_html.escape(result_name)}</b>&quot;]')
    header = (f'<span style="color:{_LAZY_COLOR}"><b>xr.Dataset [lazy]</b></span>'
              f' — stored in context, reference as {ref}')
    body = '<br>'.join('&nbsp;&nbsp;' + r for r in rows)
    return header + '<br>' + body

