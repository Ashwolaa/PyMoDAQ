# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-run T-012 rework r1)

## Done
- T-pymodaq_utils-012 reworked (run 2026-11-24-run-T-pymodaq_utils-012-r1), branch
  agent/pymodaq_utils/refactor/2026-11-24-pymodaq-config-dir, force-pushed (78452fba9). No PR yet.
- Fixed the 5 review findings: sticky `_under_pytest()` so the atexit save stays guarded; under pytest save() writes only
  if config_path is inside PYMODAQ_CONFIG_DIR (else warn + return); monkeypatch for _modified_config; exact assertions
  + cache_clear in finally; accurate save() docstring. Two new tests (342 passed, 1 skipped on pyqt6 and pyside6).
- flake8, layering, merge_gate lint ok.

## Blocked / pending
- T-012 awaits /optimize-merge (pr-reviewer round 2). Known gap: a save before the first test starts (collection) is unguarded.
- PR body must state: new env var PYMODAQ_CONFIG_DIR; get_set_local_dir loses functools.cache attrs except cache_clear
  (accepted by owner).
- PR #20 awaits the human. T-016 blocked (branch naming vs merge_gate lint). T-011 rework pending. T-014 blocked (premise false).

## Notes
- Unverified: coverage before/after for T-012 (decider-test-change condition); plugin use of cache_info / __wrapped__.
- T-013 depends on T-012 being merged.

## Next step
/optimize-merge T-pymodaq_utils-012; then T-013.
