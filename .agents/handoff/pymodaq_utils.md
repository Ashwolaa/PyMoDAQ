# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-run T-pymodaq_utils-007 rework r1)

## Done
- T-pymodaq_utils-007 rework r1: the old branch no longer rebased on dev_agent, so the rework is on
  agent/pymodaq_utils/refactor/2026-11-22-set-logger-must-v2 (old branch registry-closed). Pushed, no PR yet.
  set_logger raises ConfigError (not SystemExit); __init__.py prints it before the generic handler; unused `import sys` removed.
  New test uses the real GlobalConfig.__call__ (patched getitem_recursive) with pytest.raises(match=...).
  Checks: flake8, layering, merge_gate lint OK; pyqt6 and pyside6 343 passed, 1 skipped each.
  logger.py coverage (logger_test.py alone) 75% -> 78%; one test added, none removed or weakened.

## Blocked / open
- Not covered: the __init__.py `except ConfigError` handler (needs a module reload test).
- task.py start left registry.jsonl dirty on the branch (written on dev_agent, then switched); I committed it on
  dev_agent by hand. Tooling bug: start should commit its registry change or write it after switching.
- PR #20 awaits the human. PR #23 awaits the human. T-016 blocked, T-011 rework pending, T-014 blocked.

## Next step
Human: `/optimize-merge T-pymodaq_utils-007` (pr-reviewer round 2, then PR; medium risk, touches tests and a public function).
