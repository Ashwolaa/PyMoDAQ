verdict: approve
public_api: yes
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-007 r3 (branch agent/pymodaq_utils/refactor/2026-11-22-set-logger-must-v2, run 2026-11-24-merge-T-pymodaq_utils-007-r3)

## Checks run
- `merge_gate.py lint`: LINT OK, 19 changed lines, product files only, trailers present.
- Diff: logger.py (+1/-3 incl. removed `import sys`), __init__.py (+3), tests/logger_test.py (+10). No reformatting of untouched lines.
- Branch test file copied to tests/logger_review_tmp_test.py and run against dev_agent code: the new test fails (dev_agent prints the message and exits), the 2 old tests pass. File deleted, `git status` clean.
- Branch tests against branch code (git archive copy in /tmp, branch src first on PYTHONPATH): 3 passed. Copy removed.
- `ConfigError` is an `Exception` subclass (config.py:298); logger.py already imported from pymodaq_utils.config, so no new import cycle.
- No `except SystemExit` anywhere in packages/ (grep), so no caller relied on the exit.

## r2 findings
1. Test stubbed `getitem_recursive`: fixed. logger_test.py:26-27 now sets a scalar `debug_level` in the real utils config via `monkeypatch.setitem`, the accessor r2 proposed.
2. Wrong comment about `debug_levels`: fixed in logger_test.py:25. The first commit message (42994c88) still says "with non-list debug_level and debug_levels"; the rework commit 2a8742cb corrects it in its body ("debug_levels is never read on this path"), as r2 asked. Not blocking.
- API note carried from r2 (for the human, not a defect): public `set_logger` now raises `ConfigError` instead of `SystemExit(-1)` on a scalar `debug_level`. Same signature, message, return type. The package import catches it and prints the message (__init__.py:40-41), so the "Couldn't create the local folder" text no longer hides it. This is what the task asks; `public_api: yes` routes the PR to the human.

## Findings
None.

outside: packages/pymodaq_utils/src/pymodaq_utils/config.py:ConfigError|docstring now incomplete | docstring says it is raised only for a missing key path; set_logger now also raises it for a wrong value type
outside: packages/pymodaq_utils/src/pymodaq_utils/__init__.py:ConfigError handler|untested | the new `except ConfigError` branch in the package import has no test (carried from r1/r2)
outside: packages/pymodaq_utils/src/pymodaq_utils/config.py:GlobalConfig.__getitem__|bypasses Config.__call__ | GlobalConfig()('utils', ...) reads through BaseConfig.__getitem__, so the singular/plural fallback in Config.__call__ never applies (carried from r2)

summary: set_logger now raises ConfigError, with the same message, instead of calling sys.exit on a scalar debug_level, the pymodaq_utils import prints that message, and a test on a real config proves it.
