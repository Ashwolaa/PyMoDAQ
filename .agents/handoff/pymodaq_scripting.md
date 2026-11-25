# Handoff: pymodaq_scripting — 2026-11-25 (max 40 lines, overwrite each run)

## Done
- T-pymodaq_scripting-001 (hygiene): PR #27 merged into dev_agent.

## Blocked
- T-pymodaq_scripting-002 (docs), branch agent/pymodaq_scripting/docs/2026-11-25 (rebased on dev_agent, pushed):
  pr-reviewer verdict `changes` (run 2026-11-25-merge-T-pymodaq_scripting-002-r1). What was changed is correct, no drift;
  three fixes needed:
  1. make_component_leco_available.rst:592 still `from pymodaq.scripting import ...` -> `pymodaq_scripting`.
  2. same file 608-609: `:class:` targets `~pymodaq.scripting.devices.*` -> `pymodaq_scripting.devices`.
     (1 and 2 = open finding docs-leco-old-import-584; the plan's range stopped at 579. Widen the task to cover them.)
  3. scripting.rst:43-44: list of methods that return no Future omits `Dashboard.get_scripting_devices()`
     (returns a dict after waiting, devices.py:237-251; used at scripting.rst:83).
  Review: .agents/reports/pymodaq_scripting/2026-11-25-pr-review-T-pymodaq_scripting-002-r1.md
- Correction to the plan: old `pymodaq.scripting` still imports (a deprecated shim that re-exports and warns,
  packages/pymodaq/src/pymodaq/scripting/__init__.py); only `.utils`/`.devices` under it are missing.

## Open findings (ranked)
1. `docs/src/developer_folder/make_component_leco_available.rst:592,608-609`: old import/targets (see Blocked) [risk: low]
2. No autodoc page for pymodaq_scripting: :class:/:mod: targets do not resolve [risk: low] (no-autodoc-pymodaq-scripting)
3. `packages/pymodaq/src/pymodaq/utils/shared_ui.py:46`: tooltip claims it also runs a Coordinator (scope pymodaq) [risk: low]
4. Only API effect of T-001: star-import no longer exports submodule names devices/utils; external use unverified.

## Next step
Rework T-pymodaq_scripting-002 with `/optimize-run T-pymodaq_scripting-002` (spec-docs applies the 3 review fixes),
then `/optimize-merge T-pymodaq_scripting-002`. No PR waiting for the human.

## Evidence
- checks on rebased head: layering 3 passed; merge_gate lint OK (101 lines, product files only, trailers)
- pyqt6 / pyside6: no package touched, no scope tests to run
- docs: only a docutils parse so far (no full Sphinx build); the PR's CI compile-doc will build it
