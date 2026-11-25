verdict: changes
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_scripting-002 r1 (merge run 2026-11-25-merge-T-pymodaq_scripting-002-r1)

Branch: agent/pymodaq_scripting/docs/2026-11-25, diff `git diff dev_agent...<branch>`: 3 .rst files, +53/-48.
merge_gate lint: `LINT OK ... 101 changed lines, product files only, trailers present` (exit 0).
Docs only: no package code, no tests needed (fails_without_fix n/a). legacy_to_current.rst untouched (hard rule 3 ok).

## Verified correct against the code
- `pymodaq_scripting` exports Actuator, Detector, Dashboard (`pymodaq_scripting/__init__.py:1-3`); `pymodaq_scripting.utils`
  holds LECOBaseWrapper, LECODeviceWrapper, Device (`utils.py:92,128,401`).
- `Dashboard.get_states` / `apply_state` exist (`devices.py:253,262`); "instrument settings and actuator values" matches the docstring.
- `run_coordinator_at_startup` is the real key (`pymodaq_utils/resources/config_template.toml:25`, used in `pymodaq/utils/leco/__init__.py:11`).
- grab toggles, returns list only from the starting call with keep=True, None otherwise (`utils.py:273-282`); stop_grab returns None
  (`utils.py:284`); snap returns None while grabbing (`utils.py:264-271`); set_settings, sign_out return None (`devices.py:106,179,223`).
- `set_director_info` "currently does nothing": body is `pass` (`utils.py:167-168`), no override in pymodaq_scripting.
- Autostart "important" note removed, as the plan asked unless confirmed (default `run_coordinator_at_startup = false`).
- common_questions.rst:47 change was the plan's "may join" item; in scope.
- Note: `pymodaq.scripting` is still importable as a deprecated shim (`packages/pymodaq/src/pymodaq/scripting/__init__.py`, emits
  deprecation_msg); only `pymodaq.scripting.utils` / `.devices` do not exist. The move to the new path is still right.

## Findings (to change)
1. docs/src/developer_folder/make_component_leco_available.rst:592 - code block still `from pymodaq.scripting import Actuator, Detector, Dashboard`
   (deprecated path); the task note "use pymodaq_scripting imports" is not done for this file. Change to `from pymodaq_scripting import ...`.
2. docs/src/developer_folder/make_component_leco_available.rst:608-609 - `:class:`~pymodaq.scripting.devices.Actuator`` / `.Detector`` targets
   point to a module that does not exist; change to `pymodaq_scripting.devices`. (Plan range said 327-579, but these are the same stale
   references in the same file; ~3 lines, well under the cap.)
3. docs/src/user_folder/scripting.rst:43-44 - the list "The exceptions are ..." reads as exhaustive but omits `Dashboard.get_scripting_devices()`,
   which talks to the Dashboard and returns a dict directly, not a Future (`devices.py:237-251`), and is used at scripting.rst:83.
   Add it to the list (e.g. "``get_scripting_devices`` (waits and returns the dict)").

No drift found: every changed line serves the task; no untouched lines reformatted.

summary: Points the scripting docs to the pymodaq_scripting package, replaces configuration calls with get_states/apply_state and documents the real grab/snap behaviour; three stale references/omissions remain to fix.
