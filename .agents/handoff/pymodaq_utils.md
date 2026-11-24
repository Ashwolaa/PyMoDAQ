# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge)

## Done
- T-pymodaq_utils-015 (hygiene): PR #21 reviewed (approve), CI green, auto-merged into dev_agent.
- T-pymodaq_utils-M12 (test-quality, drift test for entry-point group lists): rebased, checks green on head
  (pyqt6 885 passed; pyside6 885 passed on rerun after one known-flaky segfault), reviewer approve, PR #20 ready.

## Blocked / pending
- PR #20 awaits the human: it touches tests and a UI scope (packages/pymodaq/tests/utils/entrypoint_groups_sync_test.py).
  CI: only the pyside6 ubuntu segfault, which upstream/dev has too (finding tests-pymodaq.yml|tests (ubuntu-latest, pyside6)|crash, seen 3x).
- T-pymodaq_utils-016: blocked, tool-task branch naming vs merge_gate lint; owner decides (agent/pymodaq_utils/tool/2026-11-24).
- T-pymodaq_utils-011: rework pending (three review items).

## Notes
- utils.py:750 has the same unused-enumerate pattern as 731 (not cited, left alone).
- The plan still lists M12 in .agents/plans/2026-11-19-pymodaq_utils-merged.md; status was set by merge.py close.

## Next step
- Human: review and merge PR #20 (Ashwolaa/PyMoDAQ).
