# Handoff: pymodaq_utils — 2026-11-20 (/optimize-merge T-pymodaq_utils-009)

## Done
- T-009 (docstrings for six names, 51 lines): rebased on dev_agent and pushed by `merge.py start` (run 2026-11-20-merge-T-pymodaq_utils-009-r1).
  Branch agent/pymodaq_utils/docs/2026-11-19-docstrings-for-six. No PR, nothing merged.
- Checks after the rebase: flake8 0, layering 3 passed, merge_gate lint OK. pyqt6 and pyside6: 323 passed, 1 failed
  (pre-existing tests/config_test.py::test_nested_update_from_user).

## Blocked
- T-009: `merge.py ci` exit 3 (error, not red). `gh workflow run` -> HTTP 422 "Actions has been disabled for this repository"
  (Ashwolaa/PyMoDAQ). No CI result for this head. pr-reviewer was not launched; `decide` would refuse without green CI.
  `merge.py close` refuses ("nothing decided yet"), so the run is left open and the plan status is unchanged.
  Not worked around (rules.md 16).

## Open findings (ranked)
1. GitHub Actions disabled on the fork: no agent branch can get CI until the human re-enables it [risk: high for the merge loop]
2. config_test::test_nested_update_from_user fails locally on both Qt backends (pre-existing; T-008) [risk: low]
3. logger.py set_logger sys.exit(-1) on import path (T-007) [risk: medium]

## Next step
- Human: re-enable Actions on Ashwolaa/PyMoDAQ (Settings > Actions), or say how CI should run otherwise.
- Then /optimize-merge T-pymodaq_utils-009: `merge.py ci 2026-11-20-merge-T-pymodaq_utils-009-r1`, then pr-reviewer, decide, gate.
  Remaining r2 order: T-006, T-011, T-007, T-008 (T-010 independent).
