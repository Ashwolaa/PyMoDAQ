# Handoff: pymodaq_utils — 2026-11-25 (after /optimize-run T-pymodaq_utils-014, rework r2)

## Done
- T-pymodaq_utils-014 reworked (run 2026-11-25-run-T-pymodaq_utils-014-r2) on
  agent/pymodaq_utils/test-quality/2026-11-25, force-pushed. Only the r2 finding was fixed: `config_after` is read
  inside the try right after the patched reload and asserted `is GlobalConfig()` after the restoring reload.
  The specialist confirmed with a mutant that the test now fails when CONFIG is not recreated.
- Checks green: flake8 blocking set, layering, merge_gate lint (32 lines); pyqt6 and pyside6: 345 passed, 1 skipped each.

## Blocked / pending
- T-014 awaits pr-reviewer (review r3), no PR opened yet.
- PRs #25 (T-011), #24 (T-007), #20 and #23 still await the human. T-016 blocked.
- Open findings: ConfigError docstring incomplete (config.py); GlobalConfig.__getitem__ bypasses Config.__call__.
- Seen, not investigated: "--- Logging error ---" / "I/O operation on closed file" blocks in the utils suite.

## Next step
/optimize-merge T-pymodaq_utils-014
