# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge T-012 r3)

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

## Notes
- PR body must state: new env var PYMODAQ_CONFIG_DIR; get_set_local_dir loses cache_info, cache_parameters and
  __wrapped__ (owner accepted).
- Unverified: coverage before/after (decider-test-change condition); plugin use of cache_info / __wrapped__.
- Not blocking: pytest < 8.2 lacks PYTEST_VERSION, config changed only at module load outside a test is not caught.

## Next step
Human: look at why PR #22 has no checks (trigger CI), then /optimize-merge T-pymodaq_utils-012 again, or merge PR #22 by hand.
