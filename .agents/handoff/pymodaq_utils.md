# Handoff pymodaq_utils (optimize-run 2026-11-19, T-pymodaq_utils-M10 rework)
## Done
- M10 (PR #13) reworked after review r1: release_5_3.rst range now 5.3.1 to 5.3.7; contract/platforms in 5.3.5,
  extension_checks/check_extension in 5.3.7. Rebased on dev_agent, pushed with --force-with-lease (head 4ae7c7337).
- Layering test passes under pyqt6 and pyside6; CI compile-doc.yml green:
  https://github.com/Ashwolaa/PyMoDAQ/actions/runs/44562977759
## Blocked (review, need /optimize-run <id>)
- M07 (#9), M08 (#11), M09 (#12): review `changes`, not reworked yet.
## Notes
- config_test::test_nested_update_from_user fails on dev_agent too (known, pre-existing); ruff format --check fails on baseline for touched files (rule 5).
- Sphinx build only checked via CI compile-doc.
## Next step
- /optimize-merge T-pymodaq_utils-M10 (re-review), then /optimize-run for M07, M08, M09.
