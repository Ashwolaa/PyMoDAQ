# Handoff: pymodaq_scripting — 2026-11-25 (max 40 lines, overwrite each run)

## Done
- T-pymodaq_scripting-001 (hygiene): PR #27 merged into dev_agent.
- T-pymodaq_scripting-002 (docs): branch agent/pymodaq_scripting/docs/2026-11-25 pushed (commit f2f9d6aa2, 101 lines),
  awaiting pr-reviewer. scripting.rst, make_component_leco_available.rst (327-579 only), common_questions.rst:47.
  pymodaq_scripting imports; get_states/apply_state; grab() toggles, keep=True list only from the starting call;
  snap() None while grabbing; "Most methods return a Future"; autostart claim removed (run_coordinator_at_startup
  defaults false); set_director_info described as a no-op.

## Open findings (ranked)
1. `docs/src/developer_folder/make_component_leco_available.rst:592,608-609`: old pymodaq.scripting import/targets, outside T-002 range [risk: low] (findings: docs-leco-old-import-584)
2. No autodoc page for pymodaq_scripting: :class:/:mod: targets do not resolve [risk: low] (no-autodoc-pymodaq-scripting)
3. `packages/pymodaq/src/pymodaq/utils/shared_ui.py:46`: tooltip claims it also runs a Coordinator (scope pymodaq) [risk: low]
4. Only API effect of T-001: star-import no longer exports submodule names devices/utils; external use unverified.

## Blocked
- none

## Next step
`/optimize-merge T-pymodaq_scripting-002`.

## Evidence
- checks: flake8 blocking ok; layering 3 passed; merge_gate lint OK (101 lines, product files only, trailers)
- pyqt6 / pyside6: no package touched, no scope tests to run
- docs: spec-docs ran a docutils parse only (no full Sphinx build); PR CI compile-doc will build it
