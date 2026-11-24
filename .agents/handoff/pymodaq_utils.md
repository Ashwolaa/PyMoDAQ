# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-run T-pymodaq_utils-013)

## Done
- T-pymodaq_utils-013 (run 2026-11-24-run-T-pymodaq_utils-013): branch agent/pymodaq_utils/test-quality/2026-11-24, pushed, no PR yet.
  New tests/conftest.py fixture `isolated_config_dir` (PYMODAQ_CONFIG_DIR -> tmp_path, cache cleared, opt-in not autouse);
  test_load_system_config uses it and a deepcopy of TOML_DICT, assertions identical.
- Checks: flake8, layering, merge_gate lint OK; pyqt6 and pyside6: 342 passed, 1 skipped each.
- Coverage: config.py 79% before/after; config_test.py 100% before/after; config_test 36 tests before/after.
- test_nested_update_from_user already passes and isolates itself: no split task needed.

## Blocked / open
- PR #20 awaits the human. T-016 blocked (branch naming vs lint). T-011 rework pending. T-014 blocked (premise false).
- Outside the task (unfiled): atexit "I/O operation on closed file" logging noise from config.py save guard / CustomConfig
  atexit lambdas at pytest exit (unverified cause); other tests (test_get_set_config_dir, TestCopy.test_copy_default)
  still use the real user/system folders.
- Unverified: skip count (1) existed before the change.

## Next step
Human: `/optimize-merge T-pymodaq_utils-013`.
