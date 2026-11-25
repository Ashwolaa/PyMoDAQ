# Plan: pymodaq_scripting — 2026-11-25
base commit: ad00c6425   mode: run

Open findings (findings.py list --scope pymodaq_scripting --status open): none.
Scanners missing: none reported.
Dropped by triage: settings clone devices.py 99-120/172-193 (mixin changes the public hierarchy), move_abs/move_rel clone (9 lines), style-only I001/UP037/W292 (rule 5), set_director_info(parameter) (LECO RPC signature), vulture DataActuator (TYPE_CHECKING false positive), Quantity type hint (public signature, revisit on request).
Not planned: docs/src/user_folder/common_questions.rst:47 uses the old pymodaq.scripting import (compat-risk and second opinion note it; may join T-pymodaq_scripting-002 if under 300 lines).

## T-pymodaq_scripting-001 Declare the public API and drop lint noise
- scope: pymodaq_scripting   specialty: hygiene
- risk: low
- files: `packages/pymodaq_scripting/src/pymodaq_scripting/__init__.py:1` (add __all__ of Actuator, Detector, Dashboard), `packages/pymodaq_scripting/src/pymodaq_scripting/examples/dashboard_script.py:1` (drop unused Actuator, Detector), `packages/pymodaq_scripting/src/pymodaq_scripting/utils.py:60` (drop .keys())
- verdicts: decider-compat-risk: approve — re-exports unchanged, only star-import of submodule names changes and none exists in the repo; decider-triage (2nd): approve — each edit checked in code
- status: done — branch agent/pymodaq_scripting/hygiene/2026-11-25, local checks green, CI on the PR, awaiting review

## T-pymodaq_scripting-002 Fix scripting docs against the code
- scope: docs   specialty: docs
- risk: low
- files: `docs/src/user_folder/scripting.rst`, `docs/src/developer_folder/make_component_leco_available.rst:327-579`
- notes: use pymodaq_scripting imports and :class: targets; get_states/apply_state instead of get_configurations/apply_configuration; grab() toggles (devices.py:149, utils.py:273-282), keep=True returns the list only from the starting call; snap() returns None while grabbing; typo "result in set". Do not edit legacy_to_current.rst (generated). Leave out the autostart claim unless confirmed in code. Split per file if over 300 lines.
- verdicts: decider-compat-risk: approve — old paths are not importable, methods named exist in code; decider-triage (2nd): approve — checked get_states/apply_state and snap signature
- status: approved
