# Handoff: pymodaq_gui — 2026-11-27 /optimize-run T-pymodaq_gui-004 (max 40 lines, overwrite each run)

## Done
- T-pymodaq_gui-004 (run 2026-11-27-run-T-pymodaq_gui-004): spec-tool added module constant
  JSCPD_IGNORE = "**/resources/material_icons/resources/**" to .agents/scripts/scan.py, passed as
  `--ignore` to jscpd and stated in the jscpd section header; new test
  test_scan_jscpd_ignores_generated_icon_resources (.agents/tests/test_scripts.py).
- Commit 9a54c8def on agent-tool/T-pymodaq_gui-004, pushed. No PR opened (merge opens it).
- Local checks: layering 3 passed; merge_gate lint OK (30 lines, tool code only); agents tests 55 passed;
  pyqt6/pyside6: no package touched, no scope tests.
- Expected side effect: scan sha256 of every scope changes on the next scan.

## Awaiting the human
- PR #32 (T-003): risk medium, public_api yes (`.colors` GlobalColor -> QColor); add the screenshots in
  .agents/reports/pymodaq_gui/screenshots/T-pymodaq_gui-003/{before,after}_{light,dark}.png to its body.
- PR #31 (T-002), PR #30 (T-001), PR #29 (T-005): still open.

## Open findings (ranked)
1. test-icon-qt-preexisting-fail: action_manager_test.py::test_icon_qt fails on base and branch.
2. flake8-syntaxwarning-escape-457: invalid escape '\*' at <unknown>:457 (file unidentified).
3. remaining-unused-imports (review, T-005 files).
- editor_test / editor_cache_test collection errors (QtWebEngine) are pre-existing.

## Blocked
- none.

## Queue
- Plan 2026-11-26-pymodaq_gui: no approved task left (T-004 done, awaiting review).

## Next step
- Agents: `/optimize-merge T-pymodaq_gui-004`.
- Human: review PR #32 (attach screenshots), then #31, #30, #29.

## Evidence
- branch: agent-tool/T-pymodaq_gui-004 (9a54c8def)
