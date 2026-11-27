# Handoff: pymodaq_gui — 2026-11-27 /optimize-merge (max 40 lines, overwrite each run)

## Done
- No PR merged this run.
- T-pymodaq_gui-003 (run 2026-11-27-merge-T-pymodaq_gui-003-r1): rebased on dev_agent, local checks
  green (pyqt6/pyside6: 739 passed; 1 failed + 2 errors all pre-existing), pr-reviewer approve,
  PR #32 opened, CI green (compile-doc, tests-gui, typing). Gate -> human.

## Awaiting the human
- PR #32 (T-003): registry/plan risk medium; reviewer public_api yes (`.colors` GlobalColor -> QColor,
  new static `ManagerSubEntriesModel.status_color`); touches tests; UI scope.
  PR body lacks the before/after screenshots the plan asks for: they are in
  .agents/reports/pymodaq_gui/screenshots/T-pymodaq_gui-003/{before,after}_{light,dark}.png
- PR #31 (T-002), PR #30 (T-001), PR #29 (T-005): still open.

## Open findings (ranked)
1. test-icon-qt-preexisting-fail: action_manager_test.py::test_icon_qt fails on base and branch.
2. flake8-syntaxwarning-escape-457: invalid escape '\*' at <unknown>:457 (file unidentified).
3. remaining-unused-imports (review, T-005 files).
- editor_test / editor_cache_test collection errors (QtWebEngine) are pre-existing.

## Blocked
- none.

## Queue
- Plan 2026-11-26-pymodaq_gui: T-004 (tool, scan.py jscpd ignore) `approved`, not yet run.

## Next step
- Human: review PR #32 (attach screenshots), then #31, #30, #29.
- Agents: `/optimize-run T-pymodaq_gui-004`.

## Evidence
- review: .agents/reports/pymodaq_gui/2026-11-27-pr-review-T-pymodaq_gui-003-r1.md
- CI: https://github.com/Ashwolaa/PyMoDAQ/actions/runs/46078927401 (tests-gui)
