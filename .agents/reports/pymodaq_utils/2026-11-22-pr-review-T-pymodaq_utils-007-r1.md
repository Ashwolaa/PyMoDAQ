verdict: changes
public_api: yes
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-007 r1 (branch agent/pymodaq_utils/refactor/2026-11-22-set-logger-must)

## Checks run
- `merge_gate.py lint`: LINT OK, 24 changed lines, product files only, trailers present.
- Reachability (task step 1): verified in config.py:615-624 (branch). With a non-list `debug_level` and an existing
  non-list `debug_levels`, `GlobalConfig.__call__` returns the scalar, so set_logger's non-list branch is reached.
- Branch test copied to tests/logger_review_tmp_test.py and run against dev_agent code: the new test fails
  ("set_logger must not call sys.exit"), the 2 old tests pass. File deleted, `git status` clean.
- Task match: the diff touches only the 3 files in the task, with no reformatting. The new exception is
  `ConfigError` (an Exception subclass, config.py:288), the message is unchanged, and so are the signature and return type.
- `__init__.py`: `except ConfigError as e: print(e)` comes before the generic handler, so the real message
  stays visible, as the task asks. The module docstring ("prints a message and the import goes on") is still accurate.

## Findings
- packages/pymodaq_utils/tests/logger_test.py:22-35: the task says "Test builds a real debug_level/debug_levels
  config". The test instead swaps `logger_mod.config` for a fake function, so it bypasses `GlobalConfig.__call__` and
  does not prove the reachable path. Change: keep the real `logger_mod.config` and use monkeypatch to set
  `utils.general.debug_level = 'DEBUG'` plus a scalar `debug_levels` in its loaded dict (e.g. `monkeypatch.setitem` on
  the nested dict; the exact accessor is unverified). Then call set_logger.
- packages/pymodaq_utils/tests/logger_test.py:27-35: hand-written try/except/else. Use
  `with pytest.raises(ConfigError, match='DEBUG is not a list')`. It asserts the same thing and is clearer.
  A SystemExit would still fail the test, because it is a BaseException that pytest.raises does not catch.
- packages/pymodaq_utils/src/pymodaq_utils/logger.py:7: `import sys` is now unused (no `sys.` left in the file).
  This change caused it, so remove that one line (it is not a reformat).
- Evidence: the task asks for a coverage diff and a test-agent justification. The coverage diff is in
  handoff/pymodaq_utils.md (logger.py 51% -> 53%). No test-agent justification found under .agents/: unverified/missing.
  Attach it before merge.
- API/behaviour (not a defect, for the human): public `set_logger` now raises `ConfigError` instead of `SystemExit(-1)`.
  Callers that call it at import time (e.g. pymodaq_gui/__init__.py:72, pymodaq_data/h5modules/__init__.py:8,
  pymodaq/utils/leco/utils.py:13) now raise ConfigError on import instead of ending the process. This is the intended effect.

outside: packages/pymodaq_utils/src/pymodaq_utils/__init__.py:ConfigError handler|untested | the new `except ConfigError` branch in the package import has no test
outside: packages/pymodaq_utils/src/pymodaq_utils/logger.py:set_logger|double config lookup | error message calls config(...) a second time instead of reusing log_level (pre-existing)

summary: set_logger now raises ConfigError instead of calling sys.exit on a non-list debug_level, and the package import prints its message; the test must use a real config, and the now-unused `import sys` must go.
verdict: changes
