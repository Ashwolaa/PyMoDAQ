# Handoff pymodaq_utils (optimize-merge 2026-11-19, T-pymodaq_utils-M10)
## Done
- Human merged: PR #3, #4 (M04), #5 (M01), #6 (M02), #7, #8 -> synced to registry/plan (this run: #4 #5 #6).
- This run: no candidate to merge. M10 (PR #13, draft) is blocked on review `changes`, which /optimize-merge does not retry.
## Blocked (review, need /optimize-run <id>)
- M10 (#13): extension_checks/check_extension came in 5.3.7, so the range '5.3.1 to 5.3.5' in release_5_3.rst is wrong.
- M07 (#9), M08 (#11), M09 (#12): review `changes`.
## Notes
- config_test::test_nested_update_from_user fails on dev_agent too (known, pre-existing); ruff format --check fails on baseline for touched files (rule 5).
- /optimize-run stopped on specialist_runs cap 10 (see earlier run); rework not started.
## Next step
- Raise [daily] specialist_runs in budget.toml (human) or wait for the reset, then /optimize-run T-pymodaq_utils-M10 (then M07, M08, M09), then /optimize-merge.
