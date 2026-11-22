# Handoff: pymodaq_utils — 2026-11-22 (/optimize-run T-pymodaq_utils-006)

## Done
- T-006 (delete dead plural fallbacks in Config.__call__): branch agent/pymodaq_utils/refactor/2026-11-22-delete-the-dead pushed,
  no PR yet. Flake8, layering, lint OK; pyqt6/pyside6: 328 passed, 1 skipped, 1 pre-existing fail
  (test_nested_update_from_user). Docstring rewritten; TestConfigPluralKeys added.
- PR #17 (T-M11) still awaiting the human.

## Open findings (ranked)
1. config_test::test_nested_update_from_user fails on base too (fixed by T-008) [risk: low]
2. pymodaq extension_loading_test Scanner load hangs offscreen [risk: medium]

## Blocked
- T-M06 (Scanner hang, unchanged).

## Next step
Human: `/optimize-merge T-pymodaq_utils-006`. Then T-011, T-007, T-009, T-008 in plan order.
Note: a path holding both 'backends' and 'backend' now takes the singular branch (negligible, unverified callers).
