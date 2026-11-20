# Handoff: pymodaq_utils — 2026-11-20 (/optimize-merge T-pymodaq_utils-010)

## Done
- T-010 (docs, 3 lines): PMQ100/PMQ200/PMQ300 rows in the check_plugin codes table
  (docs/src/developer_folder/instrument_plugins.rst). PR #15 merged into dev_agent (auto: low risk,
  decider-compat-risk + decider-triage + reviewer approve; CI green: compile-doc.yml).
- T-009 merged earlier (PR #14).

## Blocked
- Nothing.

## Open findings (ranked)
1. config_test::test_nested_update_from_user fails locally on both Qt backends (pre-existing; T-008) [risk: low]
2. logger.py set_logger sys.exit(-1) on import path (T-007) [risk: medium]
3. Reviewer nit: config.py:467 GlobalConfig docstring says an empty key returns configuration objects; it returns dicts.
4. Reviewer nit: PMQ200 row says the file's other checks are skipped; only PMQ202 is (PMQ201/203 already ran). Copied from the tool's hint.

## Next step
- No PR waits for the human. Remaining r2 tasks via /optimize-run: T-006, T-011, T-007, T-008.

## Evidence
- review: .agents/reports/docs/2026-11-20-pr-review-T-pymodaq_utils-010-r1.md (approve)
