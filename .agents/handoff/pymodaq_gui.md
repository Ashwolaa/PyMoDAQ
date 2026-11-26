# Handoff: pymodaq_gui — 2026-11-26 (max 40 lines, overwrite each run)

## Done
- Nothing merged or pushed. Run 2026-11-26-run-T-pymodaq_gui-004 was started, then blocked before any
  specialist ran (empty branch agent/pymodaq_gui/tool/2026-11-26 deleted locally, never pushed).

## Open findings (ranked)
1. Finding optimize-plan-approves-tool-tasks (scope tool, kind run): /optimize-plan approved a `tool`
   task that /optimize-run cannot carry [risk: low]
   - its only file `.agents/scripts/scan.py` is refused on any agent branch (merge_gate.py:74-76, rules.md 12)
   - task.py:205 names the branch agent/<pkg>/tool/<date>, not agent-tool/<name> (rules.md 3)
   - no tool specialist exists (evidence.py:18 only counts spec-*/test-agent)
2. Plan 2026-11-26-pymodaq_gui: T-001, T-002, T-003 still `proposed` (they need the owner);
   T-005 `approved` (remove unused imports; check #1515 vs roi.py:17 first).

## Blocked
- T-pymodaq_gui-004 (jscpd ignore of material_icons resources): needs the owner to either apply the
  one-line change on dev_agent directly (`--ignore "**/resources/material_icons/resources/**"` in
  scan.py's jscpd call and the jscpd section header), or to add a tool-task path to task.py/merge_gate.
  The deciders did not disagree: the plan is sound; the pipeline cannot carry it.

## Next step
- `/optimize-run T-pymodaq_gui-005` (the only approved pymodaq_gui task left).

## Evidence
- tests: none run (no product change); budget GO, runs 2/20 before this run
