# Handoff: pymodaq_utils — 2026-11-22 (/optimize-run T-pymodaq_utils-008)

## Done
- T-008 executed: branch agent/pymodaq_utils/test-quality/2026-11-22 (commit 79deef682), pushed, no PR yet.
  test_nested_update_from_user now patches pymodaq_utils.config.get_set_local_dir with distinct tmp_path
  system/user folders; assertions unchanged. It failed before on both backends (assert 'stop' in {'start': 23.0}).
- Checks: flake8/layering/lint OK; pyqt6 and pyside6 335 passed, 1 skipped.

## Open findings (ranked)
1. `tests/config_test.py` test_load_system_config — shares the real ~/.pymodaq folders and mutates global TOML_DICT [risk: low]

## Blocked
- T-007 (agent/pymodaq_utils/refactor/2026-11-22-set-logger-must): needs rework run (see review report r1).
- T-M06 (Scanner hang in pymodaq extension_loading_test, unchanged).

## Next step
/optimize-merge T-pymodaq_utils-008 (pr-reviewer, then PR). Then rework T-007; T-011, T-009 remain.

## Evidence
- tests: task.py checks, both backends -> 335 passed
- coverage diff: config.py 77% -> 77% (identical missing lines)
- traceback + coverage: .agents/reports/pymodaq_utils/2026-11-22-T-pymodaq_utils-008-testchange.md
