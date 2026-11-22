# Handoff: pymodaq_utils — 2026-11-22 (/optimize-merge T-pymodaq_utils-008)

## Done
- PR #17 (T-M11 shared input checks) and PR #18 (T-006 delete the dead) merged by the human (synced).
- T-008 reviewed (pr-reviewer: approve, no API change, fails without the fix), PR #19 opened, CI green.
  Branch agent/pymodaq_utils/test-quality/2026-11-22: test_nested_update_from_user isolated with tmp dirs.
  Review: .agents/reports/pymodaq_utils/2026-11-22-pr-review-T-pymodaq_utils-008-r1.md

## Blocked
- T-007 (agent/pymodaq_utils/refactor/2026-11-22-set-logger-must): needs rework run (see review report r1).
- T-M06 (Scanner hang in pymodaq extension_loading_test, unchanged).

## Open findings (ranked)
1. `tests/config_test.py` test_load_system_config — shares the real ~/.pymodaq folders and mutates global TOML_DICT [risk: low]

## Next step
Human: decide PR #19 (touches a test; plan has 1 approving decider, 2 needed, so no auto-merge).
Then /optimize-run to rework T-007; T-011, T-009 remain.
