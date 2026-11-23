# Handoff: pymodaq — 2026-11-23 (max 40 lines, overwrite each run)

## Done
- Nothing merged this run.
- Earlier (2026-11-22): T-pymodaq_utils-M12 wrote packages/pymodaq/tests/utils/entrypoint_groups_sync_test.py
  (checks the entry-point group lists in pymodaq_utils/plugin_tools/checks.py and pymodaq/utils/daq_utils.py do not drift).

## Blocked
- T-pymodaq_utils-M12 (agent/pymodaq/test-quality/2026-11-22), run 2026-11-23-merge-T-pymodaq_utils-M12-r1, NOT closed:
  - merge.py start rebased and pushed the branch (head changed), so task.py checks were required.
  - static checks pass (flake8 0, layering 3 passed, merge_gate lint OK, 10 changed lines).
  - `task.py checks --backend pyqt6` (packages/pymodaq suite) stalled in 3 attempts: ~2% CPU, process in poll,
    ~16% of tests after 19 min; pytest-xvfb warns "Xvfb not found". The pyside6 run was never reached.
    The same suite gave 881 passed on 2026-11-22. pr-reviewer was NOT launched (step b failed first).
  - Finding filed: pyqt6-suite-stalls-2026-11-23 (scope pymodaq).

## Next step
- Find out why the pymodaq pyqt6 suite stalls here (a test waiting on a thread/poll; Xvfb absent?), then rerun
  /optimize-merge pymodaq. The branch itself only adds a 10-line test.
- Separately waiting for rework: T-pymodaq_utils-011 (see handoff/pymodaq_utils.md).
