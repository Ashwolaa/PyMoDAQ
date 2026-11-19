# Handoff pymodaq_utils (optimize-merge 2026-11-19)
## Done
- Human merged: PR #3 (001), #7 (M03), #8 (M05) -> synced to registry/plan.
- Rebased M01/M02/M04 on dev_agent (clean), force-pushed, re-tested; reviews approve (r1); PRs #4, #5, #6 made ready, CI green.
## Awaiting the human (no auto-merge)
- PR #6 (M02 ThreadCommand attributes=): touches tests.
- PR #5 (M01 extract_authors): medium risk, decider veto in plan, touches tests.
- PR #4 (M04 exception hygiene): only 1 approving decider.
## Blocked (review, need /optimize-run <id>)
- M07 (#9), M08 (#11), M09 (#12), M10 (#13): review `changes`.
## Notes
- config_test::test_nested_update_from_user fails on dev_agent too (known, pre-existing); ruff format --check fails on baseline for touched files (not reformatted, rule 5).
## Stopped (2026-11-19 /optimize-run T-pymodaq_utils-M10)
- budget.py check: STOP, specialist_runs 10 >= cap 10. No rework started; nothing changed on the branch.
- M10 review finding: extension_checks/check_extension came in 5.3.7, so the range '5.3.1 to 5.3.5' in release_5_3.rst is wrong.
  Branch agent/pymodaq_utils/docs-release-note/2026-11-19 (PR #13), plan status still blocked (review).
## Next step
- Raise [daily] specialist_runs in budget.toml (human) or wait for the reset, then rerun /optimize-run T-pymodaq_utils-M10 (step 4b).
- Meanwhile review PR #6, then #4, then #5.
