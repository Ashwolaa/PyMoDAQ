# Handoff: pymodaq_utils — 2026-11-25 (after /optimize-merge T-pymodaq_utils-014 r2)

## Done
- Nothing merged this run. T-014 branch agent/pymodaq_utils/test-quality/2026-11-25 rebased on dev_agent and
  force-pushed; static, pyqt6, pyside6 checks pass (345 passed, 1 skipped each).

## Blocked / pending
- T-pymodaq_utils-014 blocked: pr-reviewer r2 verdict `changes`
  (.agents/reports/pymodaq_utils/2026-11-25-pr-review-T-pymodaq_utils-014-r2.md).
  The `assert pymodaq_utils.CONFIG is GlobalConfig()` (line 29) runs after the restoring reload, so it can
  never fail (mutant confirmed). Fix: inside the try, right after the patched reload, store
  `config_after = getattr(pymodaq_utils, 'CONFIG', None)`; after the block assert `config_after is GlobalConfig()`.
  The r1 `reloaded is pymodaq_utils` finding is fixed. No PR opened.
- PRs #25 (T-011), #24 (T-007), #20 and #23 still await the human. T-016 blocked.
- Open findings: ConfigError docstring incomplete (config.py); GlobalConfig.__getitem__ bypasses Config.__call__.
- Seen, not investigated: "--- Logging error ---" / "I/O operation on closed file" blocks in the utils suite.

## Next step
/optimize-run T-pymodaq_utils-014 (rework r2 per the fix above), then /optimize-merge T-pymodaq_utils-014.
The human reviews the open PRs meanwhile.
