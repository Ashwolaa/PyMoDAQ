# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-run T-pymodaq_utils-016)

## Done
- Specialist (spec-refactor) committed 729cb6648 on agent/pymodaq_utils/tool/2026-11-24 (not pushed): `sh_test()` in .agents/scripts/task.py runs test checks and layering with a throwaway HOME/USERPROFILE (PATH env expanded first). Demonstrated by hand; static checks: layering passes.

## Blocked
- T-pymodaq_utils-016, run 2026-11-24-run-T-pymodaq_utils-016: `merge_gate.py lint` refuses `.agents/scripts/task.py` on an `agent/<pkg>/tool/...` branch (rules.md 12: state/tooling files). The plan says branch `agent-tool/throwaway-home`, but `task.py start` names the branch from scope/specialty. Not worked around (rules.md 16).
  - Owner decision needed: how tool tasks get their branch (agent-tool/<name> support in task.py start / merge_gate lint), or apply the commit 729cb6648 to dev_agent by hand.
- Caveats from the task: /etc/.pymodaq not isolated; pymodaq/gui suites and Windows unverified.

## Next step
- Owner picks the route for tool tasks; then rerun /optimize-run T-pymodaq_utils-016 or cherry-pick 729cb6648.
- Still pending from before: rework T-pymodaq_utils-011 (three review items, see earlier handoff).

## Evidence
- task.py checks: layering 3 passed; merge_gate lint FAIL (above); no package touched, so no scope tests.
