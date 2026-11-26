# Handoff: pymodaq_gui — 2026-11-26 (max 40 lines, overwrite each run)

## Done
- T-pymodaq_gui-005 (remove unused/duplicate imports, 6 files, +1/-9): branch
  agent/pymodaq_gui/hygiene/2026-11-26 pushed (commit 4c51663a5), no PR yet. roi.py kept in scope:
  #1515 (commit c49d1310c) touches only viewerND.py and its test.

## Open findings (ranked)
1. Finding task-checks-collection-error-vacuous (scope tool): `task.py checks --backend` records green
   when pytest aborts on collection errors (editor_test.py, editor_cache_test.py need QtWebEngine,
   missing here), so no tests ran via task.py [risk: medium, the gate is blind]
2. Finding test-icon-qt-preexisting-fail: tests/managers/action_manager_test.py::test_icon_qt fails
   on base and branch, both backends [risk: low]
3. Finding optimize-plan-approves-tool-tasks (earlier run, still open).
4. Plan 2026-11-26-pymodaq_gui: T-001, T-002, T-003 still `proposed` (need the owner).

## Blocked
- T-pymodaq_gui-004 (jscpd ignore): tool task the pipeline cannot carry; owner applies it on dev_agent
  or adds a tool-task path to task.py/merge_gate.

## Next step
- `/optimize-merge T-pymodaq_gui-005`.

## Evidence
- tests: task.py checks: flake8 blocking ok, layering 3 passed, merge_gate lint OK (10 lines);
  pyqt6/pyside6 via task.py: "2 errors" (collection only, see finding 1).
- manual run (throwaway HOME, offscreen, --ignore the 2 editor tests), PyQt6 and PySide6 each:
  695 passed, 3 skipped, 1 xpassed, 1 failed (test_icon_qt, also fails on base HEAD~1).
- coverage diff: n/a (imports only)
