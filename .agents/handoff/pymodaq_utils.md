# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge T-012 r4: no candidate)

## Done
- T-pymodaq_utils-012: pr-reviewer r3 approved (public_api yes, behaviour_change yes, fails_without_fix yes).
  Rebased and pushed; flake8, layering, merge_gate lint, pyqt6 and pyside6 (342 passed, 1 skipped) green.
  PR #22 opened/readied on the fork.

## Blocked
- T-012 gate: `merge.py gate` could not read PR checks ("no checks found on PR 22", exit 3). Run closed as
  blocked — PR CI unavailable. Not worked around (rules.md 16). Likely cause: the fork's workflows did not
  start on the PR (unverified); check the Actions tab of Ashwolaa/PyMoDAQ.
- T-013 depends on T-012. PR #20 awaits the human. T-016 blocked (branch naming vs merge_gate lint).
  T-011 rework pending. T-014 blocked (premise false).

## Update r4
- `merge.py candidates T-pymodaq_utils-012` returned nothing (task is blocked in the plan). PR #22 now has checks:
  mypy and tests ubuntu 3.11-3.14 SUCCESS; windows tests and compile-doc still running at 2026-11-24 ~20:48Z.

## Notes
- PR body must state: new env var PYMODAQ_CONFIG_DIR; get_set_local_dir loses cache_info, cache_parameters and
  __wrapped__ (owner accepted).
- Unverified: coverage before/after (decider-test-change condition); plugin use of cache_info / __wrapped__.
- Not blocking: pytest < 8.2 lacks PYTEST_VERSION, config changed only at module load outside a test is not caught.

## Next step
Human: PR #22 checks now run; once green, merge PR #22 by hand (or unblock T-012 in the plan and rerun /optimize-merge). T-013 waits on it.
