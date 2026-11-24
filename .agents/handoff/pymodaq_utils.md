# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge T-012 r2)

## Done
- Nothing merged this run.

## Blocked
- T-pymodaq_utils-012 (branch agent/pymodaq_utils/refactor/2026-11-24-pymodaq-config-dir): pr-reviewer r2 = changes.
  Report: .agents/reports/pymodaq_utils/2026-11-24-pr-review-T-pymodaq_utils-012-r2.md. Static, layering, pyqt6, pyside6 checks pass.
  r1: 4 of 6 findings fixed. Open:
  1. config.py:320 atexit save still writes test changes to the real user file if no save() ran during a test
     (_PYTEST_SEEN not set). Fix: call _under_pytest() in BaseConfig.__init__ and __setitem__; also treat PYTEST_VERSION
     env as a pytest session; keep the narrow write rule.
  2. config_test.py:397 test_save_skipped_on_exit_path calls _under_pytest() by hand so it passes despite the leak; it must
     set a key without saving and reset _PYTEST_SEEN via monkeypatch, so it fails on the current code.
  3. save() docstring (config.py:467) untrue until 1 is fixed.
- T-013 depends on T-012 being merged. PR #20 awaits the human. T-016 blocked (branch naming vs merge_gate lint).
  T-011 rework pending. T-014 blocked (premise false).

## Notes
- PR body must state: new env var PYMODAQ_CONFIG_DIR; get_set_local_dir loses cache_info and __wrapped__ (owner accepted).
- Unverified: coverage before/after and test count (decider-test-change condition); plugin use of cache_info / __wrapped__.

## Next step
/optimize-run T-pymodaq_utils-012 (rework round 3 with the 3 points above), then /optimize-merge T-pymodaq_utils-012.
