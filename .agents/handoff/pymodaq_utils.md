# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge T-012)

## Done
- Nothing merged this run. T-pymodaq_utils-012 (PYMODAQ_CONFIG_DIR override + BaseConfig.save pytest guard) was reviewed:
  branch rebased on dev_agent and pushed; flake8, layering, pyqt6 (340 passed) and pyside6 (340 passed) ok.

## Blocked / pending
- T-pymodaq_utils-012: blocked, pr-reviewer verdict "changes" (report .agents/reports/pymodaq_utils/2026-11-24-pr-review-T-pymodaq_utils-012-r1.md):
  1. atexit.register(self.save) runs after pytest unsets PYTEST_CURRENT_TEST, so the exit save writes ~/.pymodaq;
     check for a pytest session instead of a running test, add an exit-path test.
  2. config_path cached before PYMODAQ_CONFIG_DIR is set is still written; only write when inside PYMODAQ_CONFIG_DIR, add a test.
  3. config_test.py:368 sets _modified_config on the singleton and never restores it; use monkeypatch.setattr.
  4. Loose assertions config_test.py:345 (`or` accepts any .pymodaq dir) and :359 (`!= first`; cache clear skipped on failure).
  5. Docstring at config.py:456 overclaims.
  Public API for the human: new env var PYMODAQ_CONFIG_DIR; save() skips writes under pytest; get_set_local_dir loses functools.cache attrs except cache_clear.
- PR #20 awaits the human (tests + UI scope).
- T-pymodaq_utils-016: blocked, tool-task branch naming vs merge_gate lint; owner decides.
- T-pymodaq_utils-011: rework pending (three review items).
- T-pymodaq_utils-014: blocked, premise false (no ConfigError handler in __init__.py); rewrite or drop.

## Notes
- Unverified: coverage before/after for T-012; plugin use of get_set_local_dir.cache_info / __wrapped__.
- T-013 (conftest isolation) depends on T-012 being merged.

## Next step
/optimize-run T-pymodaq_utils-012 (rework the 5 review items), then /optimize-merge again; then T-013.
