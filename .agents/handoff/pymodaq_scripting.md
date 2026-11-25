# Handoff: pymodaq_scripting — 2026-11-25 (max 40 lines, overwrite each run)

## Done
- T-pymodaq_scripting-001 (hygiene): PR #27 merged into dev_agent.
- T-pymodaq_scripting-002 (docs) rework r1 (run 2026-11-25-run-T-pymodaq_scripting-002-r1): spec-docs applied the
  three review r1 fixes in commit bd1e66779 on agent/pymodaq_scripting/docs/2026-11-25 (force-pushed, no PR yet):
  1. make_component_leco_available.rst:592 import -> `from pymodaq_scripting import ...`
  2. same file 608-609 `:class:` targets -> `~pymodaq_scripting.devices.Actuator/.Detector`
  3. scripting.rst:44-45 exceptions list now names `Dashboard.get_scripting_devices` (waits, returns a dict)
  Status: done — awaiting review (round 2 of rework).

## Open findings (ranked)
1. docs-leco-old-import-584 (make_component_leco_available.rst:592,608-609): fixed on the branch; close it once merged [risk: low]
2. No autodoc page for pymodaq_scripting: :class:/:mod: targets do not resolve [risk: low] (no-autodoc-pymodaq-scripting)
3. `packages/pymodaq/src/pymodaq/utils/shared_ui.py:46`: tooltip claims it also runs a Coordinator (scope pymodaq) [risk: low]
4. Only API effect of T-001: star-import no longer exports submodule names devices/utils; external use unverified.

## Blocked
- none. Plan correction stands: old `pymodaq.scripting` still imports (deprecated shim re-exporting with a warning,
  packages/pymodaq/src/pymodaq/scripting/__init__.py); only `.utils`/`.devices` under it are missing.

## Next step
`/optimize-merge T-pymodaq_scripting-002` (pr-reviewer re-checks the branch against review r1, then opens the PR).

## Evidence
- tests: task.py checks -> layering 3 passed; merge_gate lint OK (108 changed lines, product files only, trailers)
- pyqt6 / pyside6: no package touched, no scope tests to run
- docs: no full Sphinx build locally; the PR's CI compile-doc will build it
- coverage diff: n/a (docs only); screenshots: none
