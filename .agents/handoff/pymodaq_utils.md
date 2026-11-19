# Handoff pymodaq_utils — /optimize-merge 2026-11-19

## Done
- Merged: none (the gate sent every approved PR to the human).
- Approved by pr-reviewer, PRs ready and open on Ashwolaa/PyMoDAQ, CI green, awaiting the human:
  - #3 T-001 unused imports (touches tests: layering_test.py allowlist; UI scope)
  - #7 T-M03 Socket.check_received_length ConnectionError (medium risk, touches tests)
  - #8 T-M05 recursive_find_* paths=None default (public_api yes, touches tests)

## Blocked
- Conflicts with dev_agent (rebase aborted): T-M01 (#5), T-M02 (#6), T-M04 (#4) — rerun the tasks
  (conflict is on the "Drop .agents/ state from this PR" commit, check before rerun).
- Review `changes` (drafts stay drafts):
  - T-M07 (#9) _literal_value docstring incomplete (np.nan, np.True_/False_, tzinfo/fold, date/time forms)
  - T-M08 (#11) six undocumented members in :members: lists dropped by autodoc
  - T-M09 (#12) SERIALIZABLE is a type alias not a registry; failure handling misdescribed
  - T-M10 (#13) extension_checks/check_extension came in 5.3.7, not 5.3.5

## Notes
- tests/config_test.py::test_nested_update_from_user fails locally on dev_agent too (pre-existing, both Qt backends);
  not in CI. Worth a task of its own.
- CI flake: ubuntu 3.12 pyside6 job on PR #3 failed once, green on rerun.
- Not picked up: M06, M11, M12 (proposed, not executed).

## Next step
Review and merge PR #3 (oldest awaiting the human), then #7, #8.
