# Handoff: pymodaq_utils — 2026-11-22 (/optimize-merge T-pymodaq_utils-006)

## Done
- T-006 (delete dead plural fallbacks in Config.__call__): pr-reviewer approved (no public API, no behaviour change),
  PR #18 opened, CI green. Not auto-merged: touches tests (config_test.py).
- PR #17 (T-M11) still awaiting the human.

## Open findings (ranked)
1. config_test::test_nested_update_from_user fails on base too (fixed by T-008) [risk: low]
2. pymodaq extension_loading_test Scanner load hangs offscreen [risk: medium]
3. Edge case in T-006: a path holding both 'backends' and 'backend' now takes the singular branch (no such path in templates/callers).

## Blocked
- T-M06 (Scanner hang, unchanged).

## Next step
Human: review and merge PR #18 (tests added only: TestConfigPluralKeys), then PR #17.
Then /optimize-run for T-011, T-007, T-009, T-008 in plan order.
Review report: .agents/reports/pymodaq_utils/2026-11-22-pr-review-T-pymodaq_utils-006-r1.md
