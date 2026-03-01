"""Live synchronisation worker for the DataMixer GUI.

``LiveSyncWorker`` must be moved to a dedicated ``QThread`` via
``moveToThread()``.  It owns the H5 file handle exclusively — the main thread
must **not** touch the file while the worker is running.

Thread communication
--------------------
* State is pushed to the worker via *queued* signals (``set_watched``,
  ``set_formulas``, ``set_xr_ctx_computed``, ``set_interval``) so every
  mutation runs inside the worker's event loop.
* Results are delivered back to the main thread via ``computed_sig``,
  ``error_sig``, and ``status_sig`` (Qt auto-queues cross-thread signals).

SWMR strategy
-------------
1. Try to open the file normally (``locking=False``).
2. If that fails (file is locked by the scan writer), retry with h5py in
   SWMR reader mode.
3. On each tick, call ``refresh_datasets()`` (SWMR) or close/reopen (tables).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import numpy as np
from qtpy.QtCore import QObject, QTimer, Signal, Slot

from pymodaq_data.h5modules.saving import H5SaverLowLevel
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq.extensions.data_mixer.gui.incremental import IncrementalTracker
from pymodaq.extensions.data_mixer.gui.formatters import _wrap_result
from pymodaq.extensions.data_mixer.parser import (
    extract_data_names,
    replace_names_in_formula_xr,
)

logger = set_logger(get_module_name(__file__))


class LiveSyncWorker(QObject):
    """Background worker that polls an H5 file and recomputes changed formulas.

    Signals
    -------
    computed_sig(name, dwa)
        Emitted once per updated formula result.
    error_sig(msg)
        Emitted on errors during polling or formula evaluation.
    status_sig(msg)
        Human-readable status string for the GUI status bar.
    """

    computed_sig = Signal(str, object)   # (name, DataWithAxes)
    error_sig    = Signal(str)
    status_sig   = Signal(str)

    def __init__(
        self,
        h5_path: Path,
        poll_interval_ms: int = 1000,
    ):
        super().__init__()
        self._h5_path = Path(h5_path)
        self._poll_interval_ms = poll_interval_ms

        self._watched_names: list[str] = []
        self._formula_registry: dict[str, str] = {}   # output_name → formula_str
        self._xr_ctx_computed: dict = {}              # output_name → xr.Dataset
        self._deps: dict[str, set[str]] = {}          # output_name → {input_names}

        self._h5saver = None
        self._swmr = False
        self._h5_base = '/RawData'   # path prefix under which data nodes live
        self._computing = False
        self._tracker = IncrementalTracker()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ── setters called from main thread (queued signals) ──────────────────────

    @Slot(list)
    def set_watched(self, names: list[str]) -> None:
        """Set the list of H5 full names to include in each refresh."""
        self._watched_names = list(names)

    @Slot(dict)
    def set_formulas(self, registry: dict[str, str]) -> None:
        """Update the formula registry and rebuild the dependency map."""
        self._formula_registry = dict(registry)
        self._rebuild_deps()

    @Slot(dict)
    def set_xr_ctx_computed(self, ctx: dict) -> None:
        """Synchronise the already-computed xarray context."""
        self._xr_ctx_computed = dict(ctx)

    @Slot(int)
    def set_interval(self, ms: int) -> None:
        """Change the polling interval (takes effect immediately if running)."""
        self._poll_interval_ms = ms
        if self._timer.isActive():
            self._timer.setInterval(ms)

    # ── lifecycle ──────────────────────────────────────────────────────────────

    @Slot()
    def start(self) -> None:
        """Open the H5 file and start the poll timer.  Runs in worker thread."""
        try:
            self._open_h5()
        except Exception as exc:
            self.error_sig.emit(f'Cannot open {self._h5_path.name}: {exc}')
            return
        # Detect the browse root used by _collect_h5_datasets in the main thread
        try:
            self._h5saver.get_node('/RawData')
            self._h5_base = '/RawData'
        except Exception:
            self._h5_base = '/'
        self._tracker.reset()
        self._timer.start(self._poll_interval_ms)
        self.status_sig.emit('Live sync started')

    @Slot()
    def stop(self) -> None:
        """Stop the poll timer and close the H5 handle."""
        self._timer.stop()
        self._close_h5()
        self.status_sig.emit('Live sync stopped')

    # ── polling loop ──────────────────────────────────────────────────────────

    @Slot()
    def _tick(self) -> None:
        """Called by QTimer; guarded against re-entrant execution."""
        if self._computing:
            return
        self._computing = True
        try:
            self._do_tick()
        except Exception as exc:
            self.error_sig.emit(str(exc))
        finally:
            self._computing = False

    def _do_tick(self) -> None:
        if not self._watched_names and not self._formula_registry:
            return

        import xarray as xr

        xr_ctx_watched = self._refresh_watched()
        if not xr_ctx_watched:
            return

        ts = self._read_timestamps()
        changed = self._tracker.changed_names(xr_ctx_watched, ts_dataset=ts)
        if not changed:
            return

        # Full eval context: refreshed H5 data + already-computed variables
        xr_ctx: dict = dict(xr_ctx_watched)
        xr_ctx.update(self._xr_ctx_computed)

        for name, formula in self._formula_registry.items():
            deps = self._deps.get(name, set())
            if deps and not (deps & changed):
                continue   # none of this formula's inputs changed

            try:
                formula_eval, _ = replace_names_in_formula_xr(
                    formula,
                    computed_names=set(self._xr_ctx_computed),
                )
                result = eval(formula_eval, {'np': np, 'xr': xr, '_xr': xr_ctx})
                dwa = _wrap_result(result, name)

                # Store back so chained formulas can reference this result
                if isinstance(result, xr.DataArray):
                    self._xr_ctx_computed[name] = result.to_dataset(name=name)
                elif isinstance(result, xr.Dataset):
                    self._xr_ctx_computed[name] = result

                self.computed_sig.emit(name, dwa)
                changed.add(name)   # downstream formulas may depend on this

            except Exception as exc:
                self.error_sig.emit(f'Formula "{name}": {exc}')

        self.status_sig.emit(f'Synced {time.strftime("%H:%M:%S")}')

    # ── H5 file management ────────────────────────────────────────────────────

    def _open_h5(self) -> None:
        """Open the H5 file, falling back to SWMR reader if locked."""
        self._h5saver, self._swmr = H5SaverLowLevel.open_for_reading(self._h5_path, force_swmr=True)

    def _close_h5(self) -> None:
        if self._h5saver is not None:
            try:
                self._h5saver.close_file()
            except Exception as exc:
                logger.debug(f'Error closing H5 handle: {exc}')
            self._h5saver = None

    def _refresh_watched(self) -> dict:
        """Return ``{rel_path: xr.Dataset}`` for all watched H5 datasets.

        The file handle is kept open between ticks — no close/reopen.

        * SWMR mode: call ``refresh_datasets()`` so the reader sees data
          written since the handle was opened (no re-open needed).
        * Non-SWMR mode: read directly from the existing handle.  Data may
          lag behind the writer, but there are *zero* extra file-open calls
          and therefore *zero* HDF5 threading errors.

        Watched names are relative H5 paths such as
        ``'Scan000/Detector000/CH0'``; the absolute path is constructed by
        prepending ``self._h5_base`` (e.g. ``'/RawData'``).
        """
        if self._h5saver is None or not self._watched_names:
            return {}

        if self._swmr:
            try:
                from pymodaq_data.h5modules.swmr import refresh_datasets
                refresh_datasets(self._h5saver.h5file)
            except Exception as exc:
                logger.debug(f'SWMR refresh failed: {exc}')

        from pymodaq_data.h5modules.data_saving import DataLoader
        loader = DataLoader(self._h5saver)
        xr_ctx: dict = {}
        for rel_path in self._watched_names:
            abs_path = f'{self._h5_base}/{rel_path}'.replace('//', '/')
            try:
                dwa = loader.load_data(abs_path)
                xr_ctx[rel_path] = dwa.to_xarray()
            except Exception as exc:
                logger.warning(f'Failed to load watched dataset {rel_path!r}: {exc}')
        return xr_ctx

    def _read_timestamps(self) -> Optional[np.ndarray]:
        """Read the flat timestamps array if the file has one, else ``None``."""
        if self._h5saver is None:
            return None
        try:
            from pymodaq_data.h5modules.data_saving import DataLoader
            loader = DataLoader(self._h5saver)
            dte = loader.load_all('/')
            for full_name in dte.get_full_names():
                if 'Timestamps' in full_name or 'ElapsedTime' in full_name:
                    dwa = dte.get_data_from_full_name(full_name)
                    return dwa.data[0].flatten()
        except Exception as exc:
            logger.debug(f'Cannot read Timestamps node: {exc}')
        return None

    # ── helpers ────────────────────────────────────────────────────────────────

    def _rebuild_deps(self) -> None:
        """Rebuild the ``output_name → {referenced input names}`` map."""
        self._deps = {}
        for name, formula in self._formula_registry.items():
            try:
                self._deps[name] = set(extract_data_names(formula))
            except Exception as exc:
                logger.warning(f'Cannot parse deps for formula {name!r}: {exc}')
                self._deps[name] = set()
