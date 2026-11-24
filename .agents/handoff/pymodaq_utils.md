# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge T-pymodaq_utils-013)

## Done
- T-pymodaq_utils-012 merged (PR #22).
- T-pymodaq_utils-013: pr-reviewer approved, PR #23 opened, CI green (compile-doc, tests-utils, typing).
  Opt-in `isolated_config_dir` fixture (tests/conftest.py); test_load_system_config isolated, deepcopy of TOML_DICT.
  Checks after rebase: lint, layering, merge_gate lint OK; pyqt6 and pyside6 342 passed, 1 skipped each.

## Blocked / open
- PR #20 awaits the human. T-016 blocked (branch naming vs lint). T-011 rework pending. T-014 blocked (premise false).
- Findings filed by pr-reviewer: TestCopy (config_test.py) still writes test.toml to the real ~/.pymodaq/config;
  atexit "Logging error" at interpreter exit for "Not saving config" (unverified whether dev_agent prints it too).
- Not done: before/after coverage comparison from T-012's conditions (reviewer did not run it; implementer reported config.py 79% before/after).

## Next step
Human: review and merge PR #23 (medium risk, touches tests: gate left it open for the human).
