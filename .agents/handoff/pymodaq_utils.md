# Handoff: pymodaq_utils — 2026-11-25 (after /optimize-merge T-pymodaq_utils-014)

## Done
- T-pymodaq_utils-014 executed earlier (test for the ConfigError handler, package_import_test.py, 29 lines, test only).
  Rebased on dev_agent; flake8, layering, lint OK; pyqt6 and pyside6: 345 passed, 1 skipped.

## Blocked / pending
- T-pymodaq_utils-014 blocked by pr-reviewer (verdict: changes, no PR opened). Branch
  agent/pymodaq_utils/test-quality/2026-11-25. Report: .agents/reports/pymodaq_utils/2026-11-25-pr-review-T-pymodaq_utils-014-r1.md
  - line 29 `hasattr(pymodaq_utils, 'CONFIG')` always passes after reload: use monkeypatch.delattr(pymodaq_utils, 'CONFIG')
    before the patched reload, then assert CONFIG is GlobalConfig() afterwards.
  - line 28 comment must match that check; line 25 `reloaded is pymodaq_utils` is vacuous: drop or replace.
- PRs #25 (T-011), #24 (T-007), #20 and #23 still await the human. T-016 blocked.
- Open findings: ConfigError docstring incomplete (config.py); GlobalConfig.__getitem__ bypasses Config.__call__.
- Seen, not investigated: "--- Logging error ---" blocks in the utils suite (6 with or without the new test).

## Next step
/optimize-run T-pymodaq_utils-014 to rework the test per the review, then /optimize-merge T-pymodaq_utils-014.
Then the human reviews the open PRs.
