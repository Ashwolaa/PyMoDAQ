"""Shared formatting and result-coercion helpers for the DataMixer GUI.

This module centralises:

* ``_collect_h5_datasets`` — walk an H5 file and return all data nodes
* ``_wrap_result``         — coerce any eval() return value to a DataWithAxes
* ``_format_xr_html``     — HTML summary of an xr.Dataset
* ``_format_dwa_html``    — HTML summary of a DataWithAxes
"""
import html as _html

import numpy as np

from pymodaq_data.data import DataWithAxes, DataSource
from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))


# ── H5 dataset collection ─────────────────────────────────────────────────────

def _collect_h5_datasets(h5saver) -> dict:
    """Walk *h5saver*'s tree and return ``{rel_path: xr.Dataset}`` for every
    data node (array whose ``data_type`` attribute contains ``'data'``).

    *rel_path* is the H5 path of the array's **parent group**, relative to the
    ``/RawData`` group (or to the root when ``/RawData`` is absent).

    For a typical PyMoDAQ scan the returned keys look like::

        'Scan000/Detector000/CH0'
        'Scan001/Detector000/CH0'

    Using the full relative path guarantees that datasets from different scans
    are never overwritten even when they share the same detector and channel
    names.

    Why parent-group path, not the array path?
    -------------------------------------------
    A single "channel" may contain several data arrays in the same group
    (e.g. ``Data00``, ``Data01``).  ``DataLoader.load_data(..., load_all=True)``
    collects them all when given *any* array in the group.  We therefore de-
    duplicate by parent path and call ``load_data`` only once per group.
    """
    from pymodaq_data.h5modules.data_saving import DataLoader
    from pymodaq_data.h5modules.backends import GROUP

    loader = DataLoader(h5saver)

    try:
        h5saver.get_node('/RawData')
        base = '/RawData'
    except Exception:
        base = '/'

    results: dict = {}
    seen_parents: set = set()

    for node in h5saver.walk_nodes(base):
        # data_type is set on ARRAY nodes (CARRAY/EARRAY), never on GROUPs
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

        # Relative path from base (e.g. 'Scan000/Detector000/CH0')
        rel = parent_path[len(base):].lstrip('/')
        if not rel:
            # Arrays stored directly under the base — use the array name
            rel = node.path[len(base):].lstrip('/').split('/')[0] or 'data'

        try:
            dwa = loader.load_data(node.path, load_all=True)
            results[rel] = dwa.to_xarray()
        except Exception as exc:
            logger.warning(f'Failed to load dataset at {rel!r}: {exc}')

    return results


# ── H5 name + lightweight info collection (no data loading) ──────────────────

def _collect_h5_names_and_info(h5saver) -> tuple:
    """Single-pass walk: return ``(names, info)`` without loading any array data.

    ``names`` is a list of rel_path strings (same as :func:`_collect_h5_names`).
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


# ── H5 name-only collection (no data loading) ────────────────────────────────

def _collect_h5_names(h5saver) -> list:
    """Walk *h5saver*'s tree and return ``[rel_path, ...]`` for every data node.

    Like :func:`_collect_h5_datasets` but does **not** load any array data —
    only the node tree is traversed.  Returns a plain list of rel_path strings
    (same keys that :func:`_collect_h5_datasets` would return).

    Used by :class:`~pymodaq.extensions.data_mixer.gui.data_mixer_gui.DataMixerGUI`
    to populate the variable browser with names only, deferring data loading to
    the incremental snapshot mechanism.
    """
    from pymodaq_data.h5modules.backends import GROUP

    try:
        h5saver.get_node('/RawData')
        base = '/RawData'
    except Exception:
        base = '/'

    names: list = []
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

    return names


# ── Incremental xarray append ─────────────────────────────────────────────────

def _append_xr(existing, new_ds):
    """Concatenate *new_ds* onto *existing* along the first dimension.

    Parameters
    ----------
    existing:
        ``xr.Dataset`` already in the snapshot, or ``None`` for first load.
    new_ds:
        ``xr.Dataset`` freshly loaded from the H5 file (full reload or new
        rows only).

    Returns
    -------
    xr.Dataset
        Updated snapshot dataset.

    Notes
    -----
    When *existing* is ``None`` the function simply returns *new_ds*.
    When *existing* is present the datasets are concatenated along the first
    dimension using ``xr.concat``.  If concatenation fails (incompatible
    coords) the function falls back to returning *new_ds* directly so the
    snapshot is always in a valid state.
    """
    import xarray as xr

    if existing is None:
        return new_ds
    try:
        return xr.concat([existing, new_ds], dim=list(new_ds.dims)[0])
    except Exception as exc:
        logger.debug(f'xr.concat failed, replacing snapshot: {exc}')
        return new_ds


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
