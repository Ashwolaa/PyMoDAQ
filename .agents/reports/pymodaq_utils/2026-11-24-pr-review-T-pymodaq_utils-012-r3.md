verdict: approve
public_api: yes
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-012 r3 (run 2026-11-24-merge-T-pymodaq_utils-012-r3)
Branch: agent/pymodaq_utils/refactor/2026-11-24-pymodaq-config-dir (3 commits 8522faba1, fb1797ddc, 249c563d1; 2 files, 133+/6-)

## Checks done
- `merge_gate.py lint`: LINT OK (139 changed lines, product files only, trailers present).
- Task match: only config.py (get_set_local_dir + private _get_set_local_dir, _PYTEST_SEEN/_under_pytest, calls in BaseConfig.__init__/__setitem__, save guard) and new test classes plus `import copy` in config_test.py. No reconcile/schema work, no conftest, no reformatting of untouched lines. No drift.
- Branch test file against dev_agent code (tmp copy `config_review_tmp_test.py`, throwaway HOME, deleted, `git status` clean): 5 fail (test_env_var_sets_system_and_user_dirs, test_cache_key_includes_env_var, test_save_skipped_under_pytest, test_save_skipped_on_exit_path, test_save_skipped_when_path_outside_isolated_dir); 2 regression checks pass (expected).
- r3 test file against the r2 code (fb1797ddc, archived copy on PYTHONPATH): test_save_skipped_on_exit_path fails, the other 3 guard tests pass; on r3 code all pass. So the new test catches the r2 leak.
- End-to-end repro of the r2 leak on r3 code (throwaway HOME, one test doing `Config()['leak'] = 42`, no save): user files contain no `leak` after the session. Same script outside pytest still writes utils.toml (normal saving kept).
- Full pymodaq_utils suite on branch code copy, throwaway HOME: 340 passed, 3 skipped. Both Qt backends: unverified by me (CI).

## r2 findings
1. atexit save leaking test changes without save(): fixed. `_under_pytest()` is now called in BaseConfig.__init__ (config.py:352) and __setitem__ (config.py:414), and `PYTEST_VERSION` counts as a session marker (config.py:326). GlobalConfig.__setitem__ (config.py:590) goes through BaseConfig.__setitem__, so it is covered too.
2. test_save_skipped_on_exit_path did not model the exit path: fixed (config_test.py:394-410 resets `_PYTEST_SEEN` via monkeypatch, sets a key without save, drops PYTEST_CURRENT_TEST and PYTEST_VERSION; fails on r2 code as shown above).
3. save() docstring untrue: fixed (config.py:470-476 now matches the code: detected at creation, __setitem__ or save; writes only inside PYMODAQ_CONFIG_DIR).

## Findings
None blocking.
- Note, not blocking: with pytest < 8.2 (no PYTEST_VERSION) a config changed only at collection/import time, outside any test, is still not recorded (config.py:326). The installed pytest is 9.2.0 and pyproject does not pin a minimum (unverified for plugin environments).

## API / behaviour (for the human)
- New env var PYMODAQ_CONFIG_DIR changes the return of the public get_set_local_dir (signature unchanged; unset = old paths, verified in code and test).
- BaseConfig.save() in a process where pytest was seen (PYTEST_CURRENT_TEST or PYTEST_VERSION in environ, also inherited by subprocesses) logs a warning and writes nothing unless config_path is inside PYMODAQ_CONFIG_DIR; also applies to __del__, atexit and import-time saves (e.g. pymodaq_gui/__init__.py:115), which now log a warning in test runs.
- get_set_local_dir is no longer a functools.cache wrapper: only `cache_clear` is kept; `cache_info`, `cache_parameters`, `__wrapped__` are gone (no use in packages/; plugins unverified; owner accepted, PR body must say so).
- Coverage before/after and the decider-test-change conditions: unverified by me (test count goes up by 7).

summary: Adds a PYMODAQ_CONFIG_DIR override to get_set_local_dir and a pytest guard in BaseConfig.save that writes only inside the isolated folder; the session is now recorded at config creation and __setitem__ (plus PYTEST_VERSION), so the atexit save no longer leaks test changes, with a test that fails on the previous code.
