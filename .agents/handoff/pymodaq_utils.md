# Handoff: pymodaq_utils — 2026-11-25 (after /optimize-merge T-pymodaq_utils-014)

## Done
- T-pymodaq_utils-014 (run 2026-11-25-merge-T-pymodaq_utils-014-r3): rebased, checks green (pyqt6 and pyside6:
  345 passed, 1 skipped), pr-reviewer verdict approve (r3), PR #26 opened/readied, PR CI green.

## Blocked / pending
- PR #26 awaits the human: no approving decider in the plan (0 of 2 needed) and it touches tests
  (packages/pymodaq_utils/tests/package_import_test.py), so merge_gate refused auto-merge.
- PRs #25 (T-011), #24 (T-007), #20 and #23 still await the human. T-016 blocked.
- Open findings: ConfigError docstring incomplete (config.py); GlobalConfig.__getitem__ bypasses Config.__call__.
- Seen, not investigated: "--- Logging error ---" / "I/O operation on closed file" at exit of the utils suite
  (also on dev_agent's config_test.py alone; noted by pr-reviewer r3).

## Next step
Human reviews PR #26 (then #25, #24, #23, #20) at https://github.com/Ashwolaa/PyMoDAQ/pulls.
