# Handoff: pymodaq_gui — 2026-11-27 /optimize-merge (max 40 lines, overwrite each run)

## Done
- No PR merged in this run.
- T-pymodaq_gui-001 (mutable default args -> None, 5 files, +2 regression tests, 81 lines):
  run 2026-11-27-merge-T-pymodaq_gui-001-r1, rebased on dev_agent, pr-reviewer `approve`
  (no public API change, tests fail without the fix, 646 tests pass under pyqt6 and pyside6 with
  the editor tests ignored). PR #30 ready, CI green (tests-gui, typing, compile-doc).
  merge_gate: HUMAN — touches tests + UI scope (pymodaq_gui).

## Blocked
- none.

## Open findings (ranked)
1. task-checks-collection-error-vacuous (tool, 3x): `task.py checks --backend` stops at collection
   (editor_test / editor_cache_test need QtWebEngine), runs 0 tests, reports green as pre-existing.
2. test-icon-qt-preexisting-fail: action_manager_test.py::test_icon_qt fails on base and branch.
3. flake8-syntaxwarning-escape-457: invalid escape '\*' at line 457 of an unidentified file.
4. remaining-unused-imports (review, T-005 files).

## Queue
- Plan 2026-11-26-pymodaq_gui: T-002, T-003, T-004 `approved`, not yet run.

## Next step
- Human: review/merge PR #30 (T-001, needs a human: tests + UI scope), then PR #29 (T-005).
- Then `/optimize-run` for T-002 (hygiene), T-003 (uiux, screenshots), T-004 (tool).

## Evidence
- review: .agents/reports/pymodaq_gui/2026-11-27-pr-review-T-pymodaq_gui-001-r1.md
- checks after rebase: flake8 blocking ok, layering 3 passed, merge_gate lint OK.
