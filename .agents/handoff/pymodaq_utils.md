# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-run T-012)

## Done
- T-pymodaq_utils-012: PYMODAQ_CONFIG_DIR override (<dir>/system, <dir>/user, env var in cache key) and
  BaseConfig.save pytest guard (warn + return under PYTEST_CURRENT_TEST unless PYMODAQ_CONFIG_DIR is set).
  Branch agent/pymodaq_utils/refactor/2026-11-24-pymodaq-config-dir pushed, no PR yet (/optimize-merge opens it).
  Checks: flake8, layering, merge_gate lint ok; pyqt6 340 passed/1 skipped, pyside6 340 passed/1 skipped
  (before: 335 each, +5 new tests). Coverage config.py 80% -> 81%, config_test.py 100% -> 100%.

## Blocked / pending
- PR #20 awaits the human (tests + UI scope).
- T-pymodaq_utils-016: blocked, tool-task branch naming vs merge_gate lint; owner decides.
- T-pymodaq_utils-011: rework pending (three review items).
- T-pymodaq_utils-014: blocked, premise false (no ConfigError handler in __init__.py); rewrite or drop.

## Notes
- Not run by the specialist: pymodaq / pymodaq_gui suites (callers of get_set_local_dir); pr-reviewer should check.
- The "unset var keeps default paths" test checks the system path loosely (/etc/.pymodaq not creatable in sandbox).
- T-013 (conftest isolation, edits existing tests) may start only after T-012 is merged.

## Next step
Human: /optimize-merge T-pymodaq_utils-012; then /optimize-run T-pymodaq_utils-013.
