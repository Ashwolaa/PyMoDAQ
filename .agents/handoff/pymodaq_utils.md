# Handoff: pymodaq_utils — 2026-11-25 (after /optimize-run T-pymodaq_utils-014)

## Done
- T-pymodaq_utils-014 (test for the ConfigError handler in pymodaq_utils/__init__.py): new
  packages/pymodaq_utils/tests/package_import_test.py, 29 lines, test only, no source change.
  Branch agent/pymodaq_utils/test-quality/2026-11-25, pushed, no PR yet.
- Local checks: flake8 blocking, layering, merge_gate lint OK; pyqt6 and pyside6: 345 passed, 1 skipped.
- Note: the handler is at __init__.py:40-41 (plan said 43-44). The patch target is pymodaq_utils.logger.set_logger,
  because __init__ re-imports it on each reload; the test restores the module in a finally block.

## Blocked / pending
- PRs #25 (T-011), #24 (T-007), #20 and #23 still await the human. T-016 blocked.
- Open findings: ConfigError docstring incomplete (config.py); GlobalConfig.__getitem__ bypasses Config.__call__.
- Seen, not investigated: "--- Logging error ---" blocks ("Not saving config utils under pytest") in the utils
  suite, 6 with or without the new test.

## Next step
/optimize-merge T-pymodaq_utils-014 (pr-reviewer, then PR), then the human reviews the open PRs.
