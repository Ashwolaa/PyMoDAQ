"""Incremental change-detection helpers for the live sync worker.

Pure Python — no Qt, no H5, no xarray required at import time.
"""
from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np


class IncrementalTracker:
    """Detect which watched datasets changed between polling ticks.

    Strategy (cheapest-first):

    1. **Timestamp pre-check** — if a flat ``timestamps`` array is provided and
       the number of non-NaN entries has not changed, nothing new was written:
       return an empty set immediately.
    2. **Hash comparison** — for each dataset, SHA-1 the raw bytes of the first
       data variable.  Return the names whose digest differs from the cached one.

    Parameters
    ----------
    None — call :meth:`update` and :meth:`changed_names` in a polling loop.
    """

    def __init__(self):
        self._hashes: dict[str, str] = {}   # full_name → hex digest
        self._last_ts_count: int = -1       # # of valid (non-NaN) timestamps

    # ── public API ─────────────────────────────────────────────────────────────

    def changed_names(
        self,
        xr_ctx: dict,
        ts_dataset: Optional[np.ndarray] = None,
    ) -> set[str]:
        """Return the names of datasets that changed since the last call.

        Parameters
        ----------
        xr_ctx:
            Mapping of ``full_name → xr.Dataset`` for the watched datasets.
        ts_dataset:
            Flat 1-D array of elapsed-time timestamps (NaN = not yet written).
            When provided, used as a cheap pre-check before hashing.

        Returns
        -------
        set[str]
            Names whose data changed (or whose hash was never seen before).
        """
        if ts_dataset is not None:
            valid_count = int(np.sum(~np.isnan(ts_dataset.astype(float))))
            if valid_count == self._last_ts_count:
                return set()
            self._last_ts_count = valid_count

        changed: set[str] = set()
        for name, ds in xr_ctx.items():
            digest = self._digest(ds)
            if self._hashes.get(name) != digest:
                self._hashes[name] = digest
                changed.add(name)
        return changed

    def reset(self) -> None:
        """Clear all cached hashes and the timestamp counter."""
        self._hashes.clear()
        self._last_ts_count = -1

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _digest(ds) -> str:
        """SHA-1 of the first data variable's raw bytes, or '' on error."""
        try:
            var = next(iter(ds.data_vars.values()))
            return hashlib.sha1(var.values.tobytes()).hexdigest()
        except Exception:
            return ''
