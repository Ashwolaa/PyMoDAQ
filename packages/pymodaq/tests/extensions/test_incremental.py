"""Tests for IncrementalTracker (pure Python — no Qt required).

Covers:
  * changed_names: first-call detection (all names are "new")
  * changed_names: no change → empty set
  * changed_names: one dataset mutated → only that name returned
  * changed_names: timestamp pre-check short-circuits hash comparison
  * reset: clears caches
"""
from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from pymodaq.extensions.data_mixer.gui.incremental import IncrementalTracker


# ── helpers ───────────────────────────────────────────────────────────────────

def _ds(data: np.ndarray, name: str = 'v') -> xr.Dataset:
    """Make a minimal 1-D Dataset."""
    return xr.Dataset({name: ('x', data)})


# ── tests ─────────────────────────────────────────────────────────────────────

class TestIncrementalTracker:

    def test_first_call_all_names_changed(self):
        tracker = IncrementalTracker()
        ctx = {'a': _ds(np.ones(3)), 'b': _ds(np.zeros(3))}
        changed = tracker.changed_names(ctx)
        assert changed == {'a', 'b'}

    def test_second_call_no_change_empty_set(self):
        tracker = IncrementalTracker()
        ctx = {'a': _ds(np.ones(3))}
        tracker.changed_names(ctx)          # prime the cache
        changed = tracker.changed_names(ctx)
        assert changed == set()

    def test_mutated_dataset_detected(self):
        tracker = IncrementalTracker()
        ctx = {'a': _ds(np.ones(3)), 'b': _ds(np.zeros(3))}
        tracker.changed_names(ctx)
        # Mutate only 'a'
        ctx['a'] = _ds(np.array([1.0, 2.0, 3.0]))
        changed = tracker.changed_names(ctx)
        assert 'a' in changed
        assert 'b' not in changed

    def test_new_key_detected(self):
        tracker = IncrementalTracker()
        ctx: dict = {'a': _ds(np.ones(3))}
        tracker.changed_names(ctx)
        ctx['b'] = _ds(np.zeros(3))   # add new key
        changed = tracker.changed_names(ctx)
        assert 'b' in changed
        assert 'a' not in changed

    def test_timestamp_precheck_skips_when_count_unchanged(self):
        tracker = IncrementalTracker()
        ctx = {'a': _ds(np.ones(3))}
        ts = np.array([0.1, 0.2, np.nan])

        # Prime: valid count = 2
        tracker.changed_names(ctx, ts_dataset=ts)
        # Mutate data but keep timestamp count the same
        ctx['a'] = _ds(np.array([9.0, 9.0, 9.0]))
        changed = tracker.changed_names(ctx, ts_dataset=ts)
        # Should short-circuit — no change reported despite data mutation
        assert changed == set()

    def test_timestamp_precheck_triggers_when_count_increases(self):
        tracker = IncrementalTracker()
        ctx = {'a': _ds(np.ones(3))}
        ts_old = np.array([0.1, 0.2, np.nan])
        ts_new = np.array([0.1, 0.2, 0.3])   # one more valid entry

        tracker.changed_names(ctx, ts_dataset=ts_old)
        # Same data but new timestamp count → hash comparison runs
        changed = tracker.changed_names(ctx, ts_dataset=ts_new)
        # 'a' data didn't change, so hash matches → not in changed set
        assert 'a' not in changed

    def test_reset_clears_state(self):
        tracker = IncrementalTracker()
        ctx = {'a': _ds(np.ones(3))}
        ts = np.array([0.1, 0.2])
        tracker.changed_names(ctx, ts_dataset=ts)
        tracker.reset()
        # After reset, everything looks new again
        changed = tracker.changed_names(ctx, ts_dataset=ts)
        assert 'a' in changed

    def test_empty_context_returns_empty_set(self):
        tracker = IncrementalTracker()
        assert tracker.changed_names({}) == set()

    def test_dataset_with_no_data_vars_returns_empty_digest(self):
        """Dataset with no data vars should not crash; treated as changed once."""
        tracker = IncrementalTracker()
        ctx = {'empty': xr.Dataset()}
        changed = tracker.changed_names(ctx)
        assert 'empty' in changed   # first-call: new name
        changed2 = tracker.changed_names(ctx)
        assert changed2 == set()    # empty digest cached; same → no change
