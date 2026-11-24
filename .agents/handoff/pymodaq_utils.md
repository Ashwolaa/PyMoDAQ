# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge T-pymodaq_utils-007 r2)

## Done
- No PR merged or opened this run.
- T-pymodaq_utils-007 (branch agent/pymodaq_utils/refactor/2026-11-22-set-logger-must-v2): rebased on dev_agent and pushed;
  flake8, layering, lint OK; pyqt6 and pyside6 343 passed, 1 skipped each.

## Blocked
- T-pymodaq_utils-007: pr-reviewer r2 verdict `changes` (public_api: yes, behaviour_change: yes). Code is correct; one r1 finding open:
  logger_test.py:26 patches `config_mod.getitem_recursive` instead of building a real config.
  Fix: `general = logger_mod.config._configs['utils']._config['general']; monkeypatch.setitem(general, 'debug_level', 'DEBUG')`.
  Also fix the comment at logger_test.py:25 and the commit message: `debug_levels` is never read on this path.
  Report: .agents/reports/pymodaq_utils/2026-11-24-pr-review-T-pymodaq_utils-007-r2.md
- Findings filed: GlobalConfig.__getitem__ bypasses Config.__call__ (so its debug_levels fallback never applies);
  the ConfigError handler in __init__.py is untested.
- PR #20 awaits the human. PR #23 awaits the human. T-016 blocked, T-011 rework pending, T-014 blocked.

## Next step
`/optimize-run T-pymodaq_utils-007` (rework r2 with the test fix above), then `/optimize-merge T-pymodaq_utils-007`.
Human note: public `set_logger` raises ConfigError instead of SystemExit(-1).
