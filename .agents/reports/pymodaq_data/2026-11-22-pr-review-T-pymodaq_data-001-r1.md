verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_data-001 r1 (run 2026-11-22-merge-T-pymodaq_data-001-r1)
Branch agent/pymodaq_data/hygiene/2026-11-22, one commit 72bfaec57, 12 files, +32/-53 (85 changed lines per lint).

## 1. Task match and drift
- `merge_gate.py lint`: LINT OK (85 changed lines, product files only, trailers present).
- Every hunk maps to an item in the task block: the import removals in the listed files, F841 at data.py:1100/2108/3267
  and data_saving.py:513, E722 at hyperspy.py:142 and numpy_func.py:46, B904 at all 7 listed sites, B012 at data.py:2111
  and plotter.py:37. No reformatting of untouched lines.
- The do-not-touch items were left alone (verified in the branch tree): numpy_func.py:6 HANDLED_UFUNCS, the backends.py:12/1313
  `metadata` imports, the h5modules/utils.py:32 return in finally, the numpy_func.py:47 `return NotImplementedError`, and saving.py and all `__init__.py` files.
- hyperspy.py:16: only get_h5_data_from_node was removed; extract_axis and verify_axis_data_uniformity are kept. The
  only other mentions are comments (lines 54 and 62).
- Remaining ruff F401/F841 hits in touched files (backends.py:16 capitalize, :19 enum_checker; hyperspy.py:57 data_array;
  data.py:4225/4240 F811 append) were not in the task, so leaving them is correct.

## 2. Correctness
- Removed imports: none of them is used in its own file any more (ruff F401/F821 is clean for them on the branch tree). I grepped
  `packages/`, `docs/` and the venv site-packages (pymodaq_plugins_mock, plugin_manager) for re-imports of each
  removed name from its module: no matches. There is no `import *` from any touched module and none of them defines `__all__`.
- data.py:41 `ureg`: still exported by `pymodaq_data/__init__` (pymodaq/__init__.py:13 and data_test.py:20 import it from there).
- data_saving.py:26: the removed `from .. import DataToExport, DataDistribution` gave the same objects already imported from
  pymodaq_data.data at line 19 (pymodaq_data/__init__.py:48 re-exports them from data), so nothing changes.
- B012 data.py:2095-2111 `_get_dimension_str` and plotter.py:19-34 `register_plotter`: every `Exception` is still caught
  and the same value is returned. Only BaseException (KeyboardInterrupt/SystemExit) now propagates instead of being swallowed,
  which is what the task's B012 item asks for.
- E722 -> `except Exception` (hyperspy.py:142 module guard, numpy_func.py:46): this only stops catching BaseException.
- B904 `from e/err`: the type and message of each raised exception are unchanged; only `__cause__` is now set.
- Smoke check: I imported every changed module from the branch tree except matplotlib_plotters, because matplotlib is not
  installed in this env (same on dev_agent). register_plotter returned a list and `_get_dimension_str` gave `(|3, 4)`.

## 3. Behaviour and API
- No public name is removed from a public namespace that plugins use. The removed names were incidental module
  imports (typing, numpy, stdlib, and re-imports of names still defined elsewhere). No signature, default, return value or exception type changes.

## 4. Tests
- Hygiene task, not a bug fix: no new test is required (n/a). I did not re-run the suite. The caller reports lint, layering and
  both Qt backends green on the rebased head (unverified by me).

## 5. Docs and docstrings
- The diff has no docs or docstring changes. The commit message matches the diff.

## Findings
None blocking.

summary: Removes unused imports and tidies exception handling in pymodaq_data (unused `as e`, bare except, `raise ... from`, return moved out of finally), with no change to the public API or to behaviour on Exception paths.
