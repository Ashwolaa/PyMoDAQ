"""H5FileScanner — lightweight read-only scanner for PyMoDAQ HDF5 files.

Public API
----------
H5FileScanner
    A thin wrapper around H5SaverLowLevel that scans a file and returns dataset
    names + metadata without loading array data, and loads single datasets on demand.

wrap_result(result, name) -> DataWithAxes
    Coerce any formula-evaluation result to a DataWithAxes.  This is the
    canonical single implementation shared by the DataMixer formula engine and
    any other extension that evaluates user-supplied expressions.

Examples
--------
Scan a file and inspect metadata without loading any arrays::

    from pymodaq_data.h5modules import H5FileScanner

    with H5FileScanner.open("scan_data.h5") as scanner:
        info = scanner.scan()          # {rel_path: "dtype shape"}
        ds   = scanner.load_dataset("Scan000/Detector000/Data2D")  # xr.Dataset

Load a dataset from an already-open handle (e.g. a persistent live-sync handle)::

    ds = H5FileScanner.load_from_handle(h5saver, "/RawData/Scan000/Detector000/Data2D")

Coerce an eval() result to DataWithAxes::

    from pymodaq_data.h5modules import wrap_result
    import numpy as np

    dwa = wrap_result(np.zeros((10, 20)), name="result")
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np

from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))


# ── H5FileScanner ─────────────────────────────────────────────────────────────

class H5FileScanner:
    """Read-only, lazy scanner for PyMoDAQ HDF5 files.

    Provides two core operations without loading array data into memory:

    * :meth:`scan` — walk the file tree and return ``{rel_path: 'dtype shape'}``
      metadata read directly from HDF5 node attributes.
    * :meth:`load_dataset` — load one named dataset as ``xr.Dataset`` on demand.

    Parameters
    ----------
    h5saver : H5SaverLowLevel
        An already-open H5 handle.  The scanner does *not* close this handle
        unless it was created via :meth:`open` (``_owns_handle`` is ``True``).
    is_swmr : bool
        Whether the file was opened in SWMR reader mode.

    Preferred usage — context manager via :meth:`open`::

        with H5FileScanner.open(path) as scanner:
            info = scanner.scan()
            ds   = scanner.load_dataset("Scan000/Detector000/Data2D")

    Borrowing an existing handle (no ownership)::

        scanner = H5FileScanner(existing_h5saver)
        info = scanner.scan()
        # do NOT call scanner.close() — you own the handle
    """

    def __init__(self, h5saver, is_swmr: bool = False):
        self._h5saver = h5saver
        self._is_swmr: bool = is_swmr
        self._owns_handle: bool = False
        try:
            h5saver.get_node('/RawData')
            self._base: str = '/RawData'
        except Exception:
            self._base = '/'

    # ── construction ──────────────────────────────────────────────────────────

    @classmethod
    def open(cls, path: Union[Path, str],
             force_swmr: bool = False) -> 'H5FileScanner':
        """Open *path* for reading and return a scanner that owns the handle.

        Parameters
        ----------
        path :
            Path to the HDF5 file.
        force_swmr :
            When ``True``, open in SWMR reader mode (h5py backend only).
            This allows reading a file simultaneously being written by a live
            scan.  When ``False`` (the default), a normal read-only open is
            attempted first with automatic SWMR fallback.

        Returns
        -------
        H5FileScanner
            Use as a context manager or call :meth:`close` explicitly.

        Raises
        ------
        RuntimeError
            If the file cannot be opened with any available backend.
        """
        from pymodaq_data.h5modules.saving import H5SaverLowLevel
        h5saver, is_swmr = H5SaverLowLevel.open_for_reading(
            Path(path), force_swmr=force_swmr)
        scanner = cls(h5saver, is_swmr)
        scanner._owns_handle = True
        return scanner

    def close(self) -> None:
        """Close the underlying H5 handle.

        Only has an effect when the scanner was created via :meth:`open`
        (``_owns_handle`` is ``True``).  Safe to call multiple times.
        """
        if self._owns_handle and self._h5saver.isopen():
            try:
                self._h5saver.close_file()
            except Exception as exc:
                logger.debug(f'Error closing H5 handle: {exc}')

    def __enter__(self) -> 'H5FileScanner':
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def h5saver(self):
        """The underlying ``H5SaverLowLevel`` handle."""
        return self._h5saver

    @property
    def base(self) -> str:
        """Base group path used for scanning (``'/RawData'`` or ``'/'``)."""
        return self._base

    @property
    def is_swmr(self) -> bool:
        """``True`` when the file was opened in SWMR reader mode."""
        return self._is_swmr

    # ── core operations ───────────────────────────────────────────────────────

    def scan(self) -> dict:
        """Walk the H5 tree; return ``{rel_path: info_str}`` without loading data.

        Only nodes whose ``data_type`` attribute contains ``'data'`` are
        included (actual measurement arrays, not axes, backgrounds, or
        metadata strings).  One entry per parent group: multiple channels
        within the same group share the same ``rel_path``.

        The *info_str* value is ``'<dtype> <shape>'`` read from HDF5 node
        attributes — no array data is transferred from disk.

        Returns
        -------
        dict
            ``{rel_path: info_str}`` ordered by tree traversal.
        """
        from pymodaq_data.h5modules.backends import GROUP

        info: dict = {}
        seen_parents: set = set()

        for node in self._h5saver.walk_nodes(self._base):
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

            rel = parent_path[len(self._base):].lstrip('/')
            if not rel:
                rel = node.path[len(self._base):].lstrip('/').split('/')[0] or 'data'

            try:
                node_attrs = getattr(node, 'attrs', {})
                shape = (node_attrs.get('shape')
                         if hasattr(node_attrs, 'get') else None)
                if shape is None:
                    shape = getattr(node, 'shape', None)
                dtype = (node_attrs.get('dtype')
                         if hasattr(node_attrs, 'get') else None)
                if dtype is None:
                    try:
                        dtype = str(node.dtype)
                    except AttributeError:
                        dtype = str(getattr(
                            getattr(node, 'atom', None), 'dtype', '?'))
                info[rel] = f'{dtype} {shape}'
            except Exception as exc:
                logger.warning(f'Cannot read metadata for {rel!r}: {exc}')
                info[rel] = '?'

        return info

    def load_dataset(self, rel_path: str) -> Optional[object]:
        """Load *rel_path* from the file and return an ``xr.Dataset``.

        *rel_path* should be one of the keys returned by :meth:`scan`.

        Parameters
        ----------
        rel_path :
            Dataset path relative to :attr:`base`
            (e.g. ``'Detector000/Data2D'``).

        Returns
        -------
        xr.Dataset or None
            ``None`` if no data node is found under the path.
        """
        abs_path = f'{self._base}/{rel_path}'.replace('//', '/')
        return self.load_from_handle(self._h5saver, abs_path)

    @staticmethod
    def load_from_handle(h5saver, abs_path: str) -> Optional[object]:
        """Load from *abs_path* in *h5saver* and return an ``xr.Dataset``.

        This static method is the low-level loading primitive exposed so that
        callers with their own open handle (e.g. a persistent live-sync loop)
        can reuse the same loading logic without creating a scanner instance.

        The method walks *abs_path*, finds the first node whose ``data_type``
        attribute contains ``'data'``, loads it as a
        :class:`~pymodaq_data.data.DataWithAxes` (including navigation axes),
        and converts it to ``xr.Dataset``.

        Parameters
        ----------
        h5saver : H5SaverLowLevel
            An open H5 handle (need not be owned by this scanner).
        abs_path : str
            Absolute HDF5 path to walk
            (e.g. ``'/RawData/Detector000/Data2D'``).

        Returns
        -------
        xr.Dataset or None
        """
        from pymodaq_data.h5modules.data_saving import DataLoader
        from pymodaq_data.h5modules.backends import GROUP

        first_array_path = None
        for node in h5saver.walk_nodes(abs_path):
            if isinstance(node, GROUP):
                continue
            try:
                if 'data' in str(node.attrs['data_type']):
                    first_array_path = node.path
                    break
            except Exception:
                continue

        if first_array_path is None:
            return None

        loader = DataLoader(h5saver)
        dwa = loader.load_data(first_array_path, load_all=True)
        return dwa.to_xarray()


# ── strip_error_vars ────────────────────────────────────────────────────────

def strip_error_vars(ds):
    """Return *ds* with its paired error/uncertainty variables removed.

    Formula evaluation contexts should use this, not the raw Dataset:
    ``xr.Dataset`` arithmetic aligns operands by variable name, so two
    operands that happen to share a channel label (e.g. both auto-labelled
    ``CH00``) would silently sum their ``CH00_error`` variables too — which is
    a plain sum, not how uncertainties actually propagate (quadrature for a
    sum, etc.). Stripping error vars before they enter eval() avoids that
    silently-wrong result; the original Dataset (with errors intact) should
    still be used for storage/display.

    Parameters
    ----------
    ds :
        Anything; only ``xr.Dataset``-like objects (with ``.attrs`` and
        ``.drop_vars``) are affected. Anything else, or a Dataset with no
        recorded error vars, is returned unchanged.

    Returns
    -------
    The input unchanged, or with ``pymodaq_error_vars`` dropped.
    """
    try:
        error_vars = ds.attrs.get('pymodaq_error_vars', [])
    except AttributeError:
        return ds
    if not error_vars:
        return ds
    return ds.drop_vars(error_vars, errors='ignore')


# ── wrap_result ───────────────────────────────────────────────────────────────

def wrap_result(result, name: str):
    """Coerce any formula-evaluation result to a named DataWithAxes.

    This is the canonical, single implementation used by the DataMixer formula
    engine and any other extension that evaluates user-supplied expressions over
    PyMoDAQ data.

    Handled types
    -------------
    xr.Dataset  (1 var)  → extract DataArray, convert via DataWithAxes.from_xarray
    xr.Dataset  (N vars) → from_xarray with attrs dropped
    xr.DataArray         → to_dataset(name=var_name), from_xarray
    DataWithAxes         → rename and return
    np.ndarray           → wrap as single-array DataWithAxes
    tuple/list of arrays → each element as a separate .data entry
    scalar               → wrap as 1-element array

    Parameters
    ----------
    result :
        The value returned by ``eval()``.
    name : str
        Output variable name; assigned to the returned DataWithAxes.

    Returns
    -------
    DataWithAxes

    Raises
    ------
    TypeError
        If *result* is none of the supported types.
    """
    from pymodaq_data.data import DataWithAxes, DataSource

    try:
        import xarray as xr
        if isinstance(result, xr.Dataset):
            # from_xarray() derives dim order from a data variable's own
            # .dims rather than the Dataset-level dim listing, so it no
            # longer matters whether arithmetic reordered them relative to
            # each other.
            dwa = DataWithAxes.from_xarray(result)
            dwa.name = name
            return dwa
        if isinstance(result, xr.DataArray):
            # promote_attrs=True carries the DataArray's own pymodaq_* attrs
            # (stamped by to_xarray() on every data variable) up to the
            # Dataset level, so from_xarray() finds pymodaq_nav_dims etc.
            # without needing its variable-level fallback.
            var_name = result.name or name
            dwa = DataWithAxes.from_xarray(result.to_dataset(name=var_name, promote_attrs=True))
            dwa.name = name
            return dwa
    except ImportError:
        pass

    if isinstance(result, DataWithAxes):
        result.name = name
        return result
    if isinstance(result, np.ndarray):
        return DataWithAxes(name, source=DataSource['calculated'], data=[result])
    if isinstance(result, (tuple, list)) and all(
            isinstance(r, np.ndarray) for r in result):
        return DataWithAxes(name, source=DataSource['calculated'],
                            data=list(result))
    if isinstance(result, (int, float, np.integer, np.floating, np.bool_)):
        return DataWithAxes(name, source=DataSource['calculated'],
                            data=[np.array([float(result)])])
    raise TypeError(
        f'Formula returned {type(result).__name__!r} — expected a DataWithAxes, '
        f'xarray Dataset/DataArray, numpy array, tuple of arrays, or scalar.')
