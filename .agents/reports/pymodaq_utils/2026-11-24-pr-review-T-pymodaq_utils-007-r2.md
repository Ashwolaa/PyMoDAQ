verdict: changes
public_api: yes
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-007 r2 (branch agent/pymodaq_utils/refactor/2026-11-22-set-logger-must-v2, run 2026-11-24-merge-T-pymodaq_utils-007-r2)

## Checks run
- `merge_gate.py lint`: LINT OK, 18 changed lines, product files only, trailers present (Agent-Run 2026-11-24-run-T-pymodaq_utils-007-r1).
- Diff: only logger.py, __init__.py and tests/logger_test.py. No reformatting of untouched lines.
- The branch test file was copied to tests/logger_review_tmp_test.py and run against dev_agent code: the new test fails, the 2 old tests pass. The file was deleted and `git status` is clean.
- Callers: no code in packages/ catches SystemExit from set_logger (grep). 127 src files call set_logger. Their import now raises ConfigError instead of exiting.
- Correction to r1's reachability claim, checked by a scratch test in /tmp: `GlobalConfig.__call__` -> `__getitem__` -> `BaseConfig.__getitem__` -> `getitem_recursive`. `Config.__call__` and its `debug_levels` fallback (config.py:647-656) are never used by set_logger. So any scalar `debug_level` reaches the raise, and `debug_levels` plays no part. The template value is a list (config_template.toml:5).

## r1 findings
- unused `import sys`: fixed (logger.py:7 removed).
- hand-written try/except: fixed (`pytest.raises(ConfigError, match=...)`).
- evidence (coverage diff, test justification): fixed. Both are in the commit message (logger.py 75% -> 78%; one test added, none removed or weakened).
- "test builds a real config": still open. See finding 1.

## Findings
1. packages/pymodaq_utils/tests/logger_test.py:26: patching `config_mod.getitem_recursive` to return 'DEBUG' for every key and every config stubs the lookup. It does not build a real debug_level config, which is the task constraint and the r1 request. Replace that line with:
   `general = logger_mod.config._configs['utils']._config['general']`
   `monkeypatch.setitem(general, 'debug_level', 'DEBUG')`
   This accessor was verified: with it the test reaches set_logger and gets SystemExit on dev_agent code. The run against the branch code is unverified but expected to pass.
2. packages/pymodaq_utils/tests/logger_test.py:25: the comment "neither debug_level nor debug_levels is a list" is wrong: `debug_levels` is never read on this path (see Checks). Change it to e.g. "scalar debug_level through the real GlobalConfig lookup". The commit-message line "with non-list debug_level and debug_levels" has the same error; fix it in the rework commit.
- API/behaviour (for the human, not a defect): public `set_logger` now raises `ConfigError` instead of `SystemExit(-1)` when `debug_level` is a scalar. Its signature, message and return type are unchanged. The `pymodaq_utils` package import catches it and prints the message (__init__.py:40-41), before the generic handler. The module docstring ("prints a message and the import goes on") is still accurate.

outside: packages/pymodaq_utils/src/pymodaq_utils/config.py:GlobalConfig.__getitem__|bypasses Config.__call__ | GlobalConfig()('utils', ...) reads through BaseConfig.__getitem__, so the singular/plural fallback in Config.__call__ (backend/debug_level/dynamic) never applies to it
outside: packages/pymodaq_utils/src/pymodaq_utils/__init__.py:ConfigError handler|untested | the new `except ConfigError` branch in the package import has no test (carried from r1)

summary: set_logger now raises ConfigError, with the same message, instead of calling sys.exit on a scalar debug_level, and the pymodaq_utils import prints that message; the test still stubs getitem_recursive and must set a real scalar debug_level instead.
