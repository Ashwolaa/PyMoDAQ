# Handoff: pymodaq — 2026-11-23 (max 40 lines, overwrite each run)

## Done
- Nothing merged this run.
- Earlier (2026-11-22): T-pymodaq_utils-M12 wrote packages/pymodaq/tests/utils/entrypoint_groups_sync_test.py
  (checks the entry-point group lists in pymodaq_utils/plugin_tools/checks.py and pymodaq/utils/daq_utils.py do not drift).

## Blocked
- T-pymodaq_utils-M12 (agent/pymodaq/test-quality/2026-11-22), run 2026-11-23-merge-T-pymodaq_utils-M12-r1:
  status "blocked — CI red" (retryable by /optimize-merge). pr-reviewer NOT launched (step b failed first).
  - merge.py start rebased and pushed the branch; static checks pass (flake8 0, layering 3 passed, lint OK, 10 lines).
  - task.py checks --backend pyqt6: 1 failed, 882 passed; NEW FAILURE tests/utils/managers/state_manager_test.py::
    TestWithSubEntries::test_non_blocking.
  - task.py checks --backend pyside6: pytest aborted (core dumped), no failing test id (likely the known
    GC-in-QThread segfault, unverified).
  - merge.py close refuses ("nothing decided yet"), so the run is NOT closed and has no ledger line. Not worked around.
  - Finding filed: pymodaq-suite-backend-failures-2026-11-23 (scope pymodaq).

## Next step
- Check whether test_non_blocking is flaky and whether the pyside6 abort also occurs on dev_agent without the branch;
  then rerun /optimize-merge pymodaq. The branch itself only adds a 10-line test.
- Separately waiting for rework: T-pymodaq_utils-011 (see handoff/pymodaq_utils.md).
