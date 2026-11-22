# Handoff: pymodaq_data — 2026-11-22

## Done
- T-pymodaq_data-001 (imports + exception hygiene): branch agent/pymodaq_data/hygiene/2026-11-22, 12 files, 85 lines.
  pr-reviewer: approve (no API change, no behaviour change on Exception paths). PR #16 open, CI green
  (compile-doc, tests-data, typing), static + pyqt6 + pyside6 checks pass (655 passed, 1 skipped each).

## Open findings (ranked)
1. `numpy_func.py:47` returns NotImplementedError instead of raising [risk: low]
2. `data.py:4225,4240` append redefined (F811) [risk: low]
3. `h5modules/exporters/hyperspy.py:57` unused data_array (F841) [risk: low]
4. Deferred in plan: B028 stacklevel, B006 mutable defaults, radon C/D in data.py.

## Blocked
- nothing blocked by review/conflict/CI.

## Next step
Human: PR #16 (Ashwolaa/PyMoDAQ) awaits you. Not auto-merged because merge_gate reported
"a decider vetoed or blocked it in the plan". Check the plan's decider notes, then merge or close.
Reviewer note: data.py ~2111 `finally: return` became a plain return after the except, so
BaseException (KeyboardInterrupt) now propagates instead of being swallowed (intended by the task).

## Evidence
- review: .agents/reports/pymodaq_data/2026-11-22-pr-review-T-pymodaq_data-001-r1.md
- merge_gate lint OK; layering_test 3 passed; flake8 blocking set 0
