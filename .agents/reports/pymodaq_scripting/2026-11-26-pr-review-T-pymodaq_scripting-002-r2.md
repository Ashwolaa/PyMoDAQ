verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_scripting-002 r2 (merge run 2026-11-26-merge-T-pymodaq_scripting-002-r2)

Branch: agent/pymodaq_scripting/docs/2026-11-25, `git diff dev_agent...<branch>`: 3 .rst files, +57/-51, commits eaa4aa9cf + da544e189 (rework).
merge_gate lint: `LINT OK ... 108 changed lines, product files only, trailers present` (exit 0).
Docs only: no package code or tests changed (fails_without_fix n/a). legacy_to_current.rst untouched (hard rule 3 ok).

## r1 findings
1. make_component_leco_available.rst:592 import -> now `from pymodaq_scripting import Actuator, Detector, Dashboard`. Fixed.
2. make_component_leco_available.rst:608-609 targets -> now `pymodaq_scripting.devices.Actuator/Detector`. Fixed.
   No `pymodaq.scripting` reference left in the three touched files (grep on the branch).
3. scripting.rst:43-45 -> `Dashboard.get_scripting_devices` added ("waits and returns a dict directly"), matches
   `devices.py:237-251` (calls `get_devices().result()`, returns a dict). Fixed.

## Re-verified against the code
- `pymodaq_scripting/__init__.py:1-3` exports Actuator, Detector, Dashboard.
- `Dashboard.get_states` -> Future[list[str]], `apply_state` -> Future[bool] (`devices.py:253,262`).
- grab toggles, returns the list only from the starting call (`utils.py:277-285`); stop_grab returns None (`utils.py:287`);
  snap returns None while grabbing (`utils.py:267-274`); set_settings, sign_out return None (`devices.py:106,179,223`).
- `set_director_info` body is `pass` (`utils.py:167-168`): "currently does nothing" is right.

## Findings
None blocking.
- nit (not required): docs/src/user_folder/scripting.rst:43-45 - the list "``grab``, ``stop_grab``, ``set_settings`` and
  ``sign_out``, ``Dashboard.get_scripting_devices``, which ..." has a misplaced "and"; reads better as
  "``grab``, ``stop_grab``, ``set_settings``, ``sign_out``, ``Dashboard.get_scripting_devices`` (which ...) and ``snap`` (which ...)".
  Wording only, every claim is correct.

No drift: every changed line serves the task; no untouched lines reformatted.

summary: Points the scripting and LECO docs to the pymodaq_scripting package, replaces configuration calls with get_states/apply_state and documents the real grab/snap/get_scripting_devices behaviour, all checked against the code.
