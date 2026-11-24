# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge T-pymodaq_utils-007 r3)

## Done
- T-pymodaq_utils-007: pr-reviewer approved (r3), PR #24 opened, CI green (static, pyqt6, pyside6: 343 passed).
  Branch agent/pymodaq_utils/refactor/2026-11-22-set-logger-must-v2. Not auto-merged: see below.

## Blocked / pending
- PR #24 awaits the human: registry and plan risk medium, a decider vetoed/blocked in the plan, 1 of 2 approving
  deciders, reviewer public_api yes, touches tests/logger_test.py.
- PR #20 and PR #23 still await the human. T-016 blocked, T-011 rework pending, T-014 blocked.
- Open findings: ConfigError docstring now incomplete (config.py); ConfigError handler in __init__.py untested;
  GlobalConfig.__getitem__ bypasses Config.__call__.

## Next step
Human reviews PR #24 first. Human note: public `set_logger` raises ConfigError (same message) instead of
SystemExit(-1); no caller in packages/ caught SystemExit.
Report: .agents/reports/pymodaq_utils/2026-11-24-pr-review-T-pymodaq_utils-007-r3.md
