# Handoff: pymodaq_utils — 2026-11-22 (/optimize-run T-pymodaq_utils-007)

## Done
- T-007: set_logger now raises ConfigError instead of sys.exit(-1); __init__.py catches ConfigError and prints its
  message (no misleading "Couldn't create the local folder"). Test added in tests/logger_test.py.
  Branch agent/pymodaq_utils/refactor/2026-11-22-set-logger-must pushed, no PR yet (/optimize-merge opens it).
- Reachability: scalar `debug_levels` in a user/system config reaches the non-list branch (GlobalConfig fallbacks
  still present on this branch since PR #18 / T-006 is unmerged).

## Open findings (ranked)
1. config_test::test_nested_update_from_user fails on base too (fixed by T-008) [risk: low]
2. logger.py: `import sys` now unused (left for minimal diff) [risk: low]
3. __init__.py ConfigError handler untested [risk: low]
4. pymodaq extension_loading_test Scanner load hangs offscreen [risk: medium]

## Blocked
- T-M06 (Scanner hang, unchanged).

## Next step
Human: /optimize-merge T-pymodaq_utils-007; PRs #17 and #18 still await review. Then T-011, T-009, T-008.

## Evidence
- tests: pyqt6 and pyside6: 324 passed, 1 failed (pre-existing test_nested_update_from_user); flake8, layering, lint OK
- coverage diff: logger.py 51% -> 53% (line 44 newly covered)
