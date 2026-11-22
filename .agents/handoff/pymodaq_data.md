# Handoff: pymodaq_data — 2026-11-22

## Done
- T-pymodaq_data-001 (imports + exception hygiene): branch agent/pymodaq_data/hygiene/2026-11-22, commit 679c91dc1, 12 files, 85 lines. Pushed, no PR yet.

## Open findings (ranked)
1. `numpy_func.py:47` returns NotImplementedError instead of raising [risk: low]
2. `data.py:4225,4240` append redefined (F811) [risk: low]
3. `h5modules/exporters/hyperspy.py:57` unused data_array (F841) [risk: low]
4. Deferred in plan: B028 stacklevel, B006 mutable defaults, radon C/D in data.py.

## Blocked
- nothing

## Next step
/optimize-merge T-pymodaq_data-001 (pr-reviewer, then PR). Reviewer note: data.py ~2111 `finally: return` became a plain return after the except, so BaseException (KeyboardInterrupt) now propagates instead of being swallowed.

## Evidence
- tests: cd packages/pymodaq_data && pytest -> 655 passed, 1 skipped under pyqt6 and pyside6
- layering_test 3 passed; flake8 blocking set 0; merge_gate lint OK
