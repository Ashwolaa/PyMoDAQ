# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-run T-012 rework r3)

## Done
- T-pymodaq_utils-012 rework (run 2026-11-24-run-T-pymodaq_utils-012-r2, commit 4238cd7ad) pushed on
  agent/pymodaq_utils/refactor/2026-11-24-pymodaq-config-dir. Fixed the 3 open review points:
  _under_pytest() now called in BaseConfig.__init__/__setitem__ and also honours PYTEST_VERSION;
  test_save_skipped_on_exit_path rewritten (fails on the old code); save() docstring corrected.
- Checks: flake8 blocking, layering, merge_gate lint, pyqt6 and pyside6 (342 passed, 1 skipped) all green.

## Blocked / pending
- T-013 depends on T-012 being merged. PR #20 awaits the human. T-016 blocked (branch naming vs merge_gate lint).
  T-011 rework pending. T-014 blocked (premise false).

## Notes
- PR body must state: new env var PYMODAQ_CONFIG_DIR; get_set_local_dir loses cache_info and __wrapped__ (owner accepted).
- Unverified: coverage before/after and test count (decider-test-change condition); plugin use of cache_info / __wrapped__.

## Next step
/optimize-merge T-pymodaq_utils-012
