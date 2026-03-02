"""Shared formatting helpers for the DataMixer GUI.

This module centralises:

* ``_format_xr_html``            — HTML summary of an xr.Dataset
* ``_format_xr_lazy_html``       — lazy HTML summary (no .values call on data vars)

H5 scanning and result coercion have moved to ``pymodaq_data.h5modules``::

    from pymodaq_data.h5modules import H5FileScanner, wrap_result
"""
import html as _html

from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))


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

