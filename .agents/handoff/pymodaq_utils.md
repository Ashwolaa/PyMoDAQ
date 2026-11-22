# Handoff pymodaq_utils (after /optimize-merge, 2026-11-22)

## Done
- PR #19 (agent/pymodaq_utils/test-quality/2026-11-22) merged into dev_agent (seen by merge.py sync).

## Blocked
- T-pymodaq_utils-011 (agent/pymodaq_utils/refactor/2026-11-22-packages-get-entrypoints), run 2026-11-22-merge-T-pymodaq_utils-011-r2:
  - start rebased + pushed (head be45c4198); static, pyqt6 and pyside6 checks all pass (335 passed each).
  - pr-reviewer verdict: changes (public_api yes, behaviour_change yes). Same three open items as r1:
    1. add a test (returns list == utils.get_entrypoints(group); pytest.warns(DeprecationWarning, match='pymodaq_utils.utils.get_entrypoints'); no dependence on installed plugins)
    2. give `.. deprecated::` a version (packages.py:174; repo style `5.3.5`)
    3. remove unused `from importlib import metadata` (packages.py:2) or comment why it stays
  - merge.py decide now worked (the r1 launch-detection refusal did not recur); task blocked, run closed.
  - Report: .agents/reports/pymodaq_utils/2026-11-22-pr-review-T-pymodaq_utils-011-r2.md

## Next step
- Rework T-011 with /optimize-run (the three fixes above), then rerun /optimize-merge pymodaq_utils.
- Since the change is public API (list instead of EntryPoints, new warning), the PR will go to the human, not auto-merge.
