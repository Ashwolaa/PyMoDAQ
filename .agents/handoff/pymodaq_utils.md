# Handoff pymodaq_utils (optimize-merge 2026-11-19, T-pymodaq_utils-M09)
## Done
- M10 (PR #13) and M09 (PR #12) merged into dev_agent (auto-merge, merge commits). M09: review r2 approve,
  branch and PR CI green, tests under pyqt6/pyside6 pass except the known config_test failure.
## Blocked (review `changes`, need /optimize-run <id>)
- M07 (#9), M08 (#11): not reworked yet (still draft PRs).
## Notes
- config_test::test_nested_update_from_user fails on dev_agent too (known, pre-existing).
- Review nit for later: set_logger can sys.exit(-1), which `except Exception` in __init__ does not catch (unverified beyond reviewer).
## Next step
- /optimize-run for M07, M08, then /optimize-merge.
