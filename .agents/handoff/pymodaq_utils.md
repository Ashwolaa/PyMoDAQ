# Handoff: pymodaq_utils — 2026-11-25 (after /optimize-run T-pymodaq_utils-014 rework r1)

## Done
- T-pymodaq_utils-014 reworked per review r1 (run 2026-11-25-run-T-pymodaq_utils-014-r1), branch
  agent/pymodaq_utils/test-quality/2026-11-25, head 3c4702c4d, force-pushed. Test only (package_import_test.py).
  - CONFIG assertion now non-vacuous: monkeypatch.delattr before the patched reload, then `CONFIG is GlobalConfig()`.
  - Vacuous `reloaded is pymodaq_utils` and its comment dropped/rewritten.
  - flake8, layering, lint OK; pyqt6 and pyside6: 345 passed, 1 skipped.
  - Mutation check (handler aborting the import -> AttributeError) reasoned, not run.

## Blocked / pending
- T-014 awaits /optimize-merge (pr-reviewer, then PR). No PR opened yet.
- PRs #25 (T-011), #24 (T-007), #20 and #23 still await the human. T-016 blocked.
- Open findings: ConfigError docstring incomplete (config.py); GlobalConfig.__getitem__ bypasses Config.__call__.
- Seen, not investigated: "--- Logging error ---" / "I/O operation on closed file" blocks in the utils suite
  (present with or without the new test).

## Next step
/optimize-merge T-pymodaq_utils-014. Then the human reviews the open PRs.
