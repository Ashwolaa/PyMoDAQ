# Handoff: pymodaq_gui — 2026-11-26 (max 40 lines, overwrite each run)

## Done
- T-pymodaq_gui-005 (remove 6 unused/duplicate imports, +1/-9): pr-reviewer approved (run
  2026-11-26-merge-T-pymodaq_gui-005-r1), PR #29 on Ashwolaa/PyMoDAQ -> dev_agent, CI green
  (compile-doc, tests-gui, typing). Not auto-merged: merge_gate requires the human for UI-scope files.
- No PR merged in this run.

## Blocked
- none in this run.

## Open findings (ranked)
1. task-checks-collection-error-vacuous (tool): `task.py checks --backend` reports "2 errors ...
   pre-existing" when pytest aborts on collection (editor_test.py, editor_cache_test.py need
   QtWebEngine), so local backend checks ran no tests; the PR's tests-gui.yml CI is the real signal.
2. remaining-unused-imports (review, roi.py and the other 5 files): more unused imports
   (e.g. LinearRegionItem, Slot in roi.py; QByteArray, QObject in pixmap.py); re-export not checked.
3. test-icon-qt-preexisting-fail: action_manager_test.py::test_icon_qt fails on base and branch.

## Queue
- Plan 2026-11-26-pymodaq_gui: T-001, T-002, T-003, T-004 `approved` (owner), not yet run.

## Next step
- Human: review and merge PR #29 (https://github.com/Ashwolaa/PyMoDAQ/pull/29), UI scope
  (subentries, pixmap, tableview, viewer0D, roi, filter): imports only, no behaviour change.
- Then `/optimize-run pymodaq_gui` for the approved T-001..T-004.

## Evidence
- review: .agents/reports/pymodaq_gui/2026-11-26-pr-review-T-pymodaq_gui-005-r1.md
- local after rebase: flake8 blocking ok, layering 3 passed, merge_gate lint OK (10 lines).
