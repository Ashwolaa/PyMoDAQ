# Handoff: pymodaq_utils — 2026-11-22 (/optimize-run T-pymodaq_utils-011)

## Done
- T-011 executed: packages.get_entrypoints now delegates to utils.get_entrypoints (function-local import).
  Branch agent/pymodaq_utils/refactor/2026-11-22-packages-get-entrypoints, pushed, no PR yet.
  Return type changes EntryPoints -> list; docstring states it and deprecation_msg is called.
  No in-repo caller of packages.get_entrypoints (all use utils); external plugins unverified.
- Checks: flake8 0, layering ok, merge_gate lint ok; pyqt6 and pyside6: 334 passed, 1 skipped, 1 failed
  (test_nested_update_from_user, pre-existing, fixed by T-008 / PR #19).

## Open findings (ranked)
1. `tests/config_test.py` test_load_system_config shares the real ~/.pymodaq folders and mutates global TOML_DICT [risk: low]

## Blocked
- T-007 (agent/pymodaq_utils/refactor/2026-11-22-set-logger-must): needs rework run (review report r1).
- T-M06 (Scanner hang in pymodaq extension_loading_test, unchanged).
- PR #19 (T-008) awaits the human (touches a test, one approving decider).

## Next step
Human: /optimize-merge T-pymodaq_utils-011 (pr-reviewer, PR). Then /optimize-run to rework T-007; T-009 remains.

## Evidence
- tests: task.py checks, both backends -> only the pre-existing failure
