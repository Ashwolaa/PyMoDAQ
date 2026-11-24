# Handoff: pymodaq_utils — 2026-11-24 (after /optimize-merge T-pymodaq_utils-011)

## Done
- T-pymodaq_utils-011 (packages.get_entrypoints delegates to utils.get_entrypoints): pr-reviewer approved r3
  (all three r2 findings fixed), PR #25 opened against dev_agent, CI green (compile-doc, tests-utils, typing).
- Local checks on the rebased head: flake8 blocking, layering, merge_gate lint (35 lines); pyqt6 and pyside6: 344 passed, 1 skipped.

## Blocked / pending
- PR #25 (T-011) awaits the human: registry risk medium, plan risk medium, public_api yes
  (return type EntryPoints -> list plus DeprecationWarning), touches packages_test.py.
- PR #24 (T-007), PR #20 and PR #23 still await the human. T-016 blocked, T-014 blocked.
- Open findings: ConfigError docstring incomplete (config.py); ConfigError handler in __init__.py untested;
  GlobalConfig.__getitem__ bypasses Config.__call__.
- Reviewer note (non-blocking): the new test uses a nonexistent group, so the equality check compares two empty lists.

## Next step
Human reviews PR #25 (https://github.com/Ashwolaa/PyMoDAQ/pull/25), then PRs #24, #20, #23.
