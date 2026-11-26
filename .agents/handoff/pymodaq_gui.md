# Handoff: pymodaq_gui — 2026-11-26 (max 40 lines, overwrite each run)

## Done
- T-pymodaq_gui-001 (mutable default args -> None, 5 files, +2 regression tests, 81 changed lines):
  run 2026-11-26-run-T-pymodaq_gui-001, commit 08522a8e7, pushed to
  agent/pymodaq_gui/hygiene/2026-11-26-fix-mutable-default. No PR yet (opened by /optimize-merge).
  Fixed bugs: h5tree_to_QTree shared pixmap_items, walk_xml_to_parameter shared params;
  read-only cleanups (browsing.show_pixmaps, viewer1Dbasic.set_axis_label, viewer.py __main__) untested.
- Earlier: T-pymodaq_gui-005 PR #29 open, awaiting the human (UI scope).

## Blocked
- none in this run.

## Open findings (ranked)
1. task-checks-collection-error-vacuous (tool, 2x): `task.py checks --backend` stops at collection
   (editor tests need QtWebEngine) and runs no tests. Manual run with editor tests ignored:
   697 passed, 1 failed (test_icon_qt), 3 skipped under PyQt6 and PySide6.
2. test-icon-qt-preexisting-fail (2x): action_manager_test.py::test_icon_qt fails on base and branch.
3. flake8-syntaxwarning-escape-457: invalid escape '\*' at line 457 of an unidentified file.
4. remaining-unused-imports (review, T-005 files).

## Queue
- Plan 2026-11-26-pymodaq_gui: T-002, T-003, T-004 `approved`, not yet run.

## Next step
- Human: `/optimize-merge T-pymodaq_gui-001`; review/merge PR #29.
- Then `/optimize-run` for T-002 (hygiene), T-003 (uiux, screenshots), T-004 (tool).

## Evidence
- local: flake8 blocking ok, layering 3 passed, merge_gate lint OK (81 lines, product files only).
- new tests failed before the fix (assert 2 == 1) under both bindings, per the specialist.
