# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-run T-pymodaq_utils-011 r2)

## Done
- T-pymodaq_utils-011 rework (owner-granted round 3): spec-refactor fixed exactly the three r2 findings in commit 0bb9cce41:
  test_get_entrypoints_delegates_and_warns (packages_test.py), `.. deprecated:: 5.4.0`, unused `importlib.metadata` import removed.
- Local checks green: flake8 blocking, layering, merge_gate lint (35 lines); pyqt6 and pyside6: 344 passed, 1 skipped.
- Branch agent/pymodaq_utils/refactor/2026-11-22-packages-get-entrypoints pushed (force-with-lease). No PR opened.

## Blocked / pending
- T-011 awaits pr-reviewer (public_api yes: return type EntryPoints -> list plus DeprecationWarning, so a human decides the merge).
- PR #24 (T-007), PR #20 and PR #23 still await the human. T-016 blocked, T-014 blocked.
- Open findings: ConfigError docstring incomplete (config.py); ConfigError handler in __init__.py untested;
  GlobalConfig.__getitem__ bypasses Config.__call__.

## Next step
`/optimize-merge T-pymodaq_utils-011`
