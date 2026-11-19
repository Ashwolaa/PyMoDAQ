# Handoff pymodaq_utils (optimize-merge 2026-11-19, T-pymodaq_utils-M10)
## Done
- M10 (PR #13) merged into dev_agent (auto-merge, merge commit). Review r2 approve; branch CI compile-doc green;
  layering test pass under pyqt6 and pyside6.
## Blocked (review `changes`, need /optimize-run <id>)
- M07 (#9), M08 (#11), M09 (#12): not reworked yet (still draft PRs).
## Notes
- config_test::test_nested_update_from_user fails on dev_agent too (known, pre-existing).
- Sphinx build only checked via CI compile-doc.
## Next step
- /optimize-run for M07, M08, M09, then /optimize-merge.
