# Handoff: pymodaq_utils — 2026-11-20 (/optimize-run T-pymodaq_utils-010)

## Done
- T-010 (docs, 3 lines): PMQ100/PMQ200/PMQ300 rows added to the check_plugin codes table in
  docs/src/developer_folder/instrument_plugins.rst. Branch agent/docs/docs/2026-11-20 pushed, commit 045a8d1cd.
  Checks: flake8 OK, layering 3 passed, lint OK; no package touched so no Qt backend tests. Docs build not run (CI on PR).
  Run 2026-11-20-run-T-pymodaq_utils-010. No PR yet.
- T-009 merged earlier (PR #14).

## Blocked
- Nothing.

## Open findings (ranked)
1. config_test::test_nested_update_from_user fails locally on both Qt backends (pre-existing; T-008) [risk: low]
2. logger.py set_logger sys.exit(-1) on import path (T-007) [risk: medium]
3. Reviewer nit: config.py:467 GlobalConfig docstring says an empty key returns configuration objects; it returns dicts.
4. rules.py line numbers in plan T-010 were off by a few lines (312/418/514/708/811 now); harmless.

## Next step
- /optimize-merge T-pymodaq_utils-010 (docs, low risk). Remaining r2 order: T-006, T-011, T-007, T-008.

## Evidence
- tests: task.py checks (flake8, layering, lint) -> OK
