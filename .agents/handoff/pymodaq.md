# Handoff: pymodaq — 2026-11-22 (max 40 lines, overwrite each run)

## Done
- T-pymodaq_utils-M12 (run 2026-11-22-run-T-pymodaq_utils-M12): new test
  packages/pymodaq/tests/utils/entrypoint_groups_sync_test.py (commit e93fe3683) checks that the entry-point group
  lists in pymodaq_utils/plugin_tools/checks.py and pymodaq/utils/daq_utils.py do not drift.
- Branch agent/pymodaq/test-quality/2026-11-22 pushed, no PR yet.

## Open findings (ranked)
1. Random PySide6 full-suite abort in packages/pymodaq (Fatal Python error: Aborted), also without the new test. Known
   upstream GC-in-QThread crash. 3 of 4 pyside6 runs aborted, 1 passed (881 passed). [risk: low]

## Blocked
- nothing

## Next step
/optimize-merge T-pymodaq_utils-M12 (pr-reviewer, then PR to dev_agent).

## Evidence
- static: flake8 blocking 0, layering 3 passed, merge_gate lint OK (10 changed lines)
- pyqt6: 881 passed, 16 skipped; pyside6: 881 passed, 16 skipped on rerun after two aborts
- test fails when one list is altered (temporary monkeypatch)
