verdict: changes
public_api: yes
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-012 r2 (run 2026-11-24-merge-T-pymodaq_utils-012-r2)
Branch: agent/pymodaq_utils/refactor/2026-11-24-pymodaq-config-dir (2 commits, 5223c6d94 + c99445096, 2 files, 123+/6-)

## Checks done
- `merge_gate.py lint`: LINT OK (129 changed lines, product files only, trailers present).
- Task match: only config.py (get_set_local_dir, new _under_pytest, save) and new test classes in config_test.py. No reconcile/schema work, no conftest, no reformatting of untouched lines. No drift seen.
- Branch test file run against dev_agent code (tmp copy `config_review_tmp_test.py`, throwaway HOME, deleted after, `git status` clean): the 5 new tests test_env_var_sets_system_and_user_dirs, test_cache_key_includes_env_var, test_save_skipped_under_pytest, test_save_skipped_on_exit_path, test_save_skipped_when_path_outside_isolated_dir fail; test_unset_keeps_default_paths and test_save_allowed_with_isolated_dir pass (regression checks, expected).
- Owner guidance followed: narrow rule (config_path must be inside PYMODAQ_CONFIG_DIR, Path.is_relative_to), no `'pytest' in sys.modules`. The dropped cache_info/__wrapped__ must be stated in the PR body (accepted by the owner).

## r1 findings
1. atexit path (config.py:459 in r1): partly fixed, still open, see finding 1 below.
2. stale config_path outside PYMODAQ_CONFIG_DIR: fixed (config.py:471-477, is_relative_to; test at config_test.py:407).
3. singleton `_modified_config` assigned without restore: fixed (monkeypatch.setattr everywhere).
4. `or` assertion on the system folder: fixed (membership in the two exact paths get_set_path can return).
5. `!= first` and skipped cache_clear: fixed (exact `==`, cache_clear in try/finally).
6. docstring untrue: still partly untrue, see finding 2.

## Findings
- packages/pymodaq_utils/src/pymodaq_utils/config.py:320 `_PYTEST_SEEN` is only set when save() itself runs during a test, so a test that changes a config (`cfg['k'] = 42`, __setitem__ at :409) without calling save() still has it written to the real user file by the atexit save (:350). Verified with the branch config.py, throwaway HOME, one test `cfg['leak'] = 42`: after the session the user exp_cfg.toml contains `leak = 42`. Same root cause for saves at collection time (e.g. pymodaq_gui/__init__.py:115 `config.save()` on import). Change: record the session independently of save(), e.g. call `_under_pytest()` in BaseConfig.__init__ and __setitem__, and also treat `PYTEST_VERSION` in environ (set by pytest >= 8.2 for the whole session, installed 9.2.0) as a session marker; keep the narrow write rule.
- packages/pymodaq_utils/tests/config_test.py:397 test_save_skipped_on_exit_path calls `_under_pytest()` by hand before removing PYTEST_CURRENT_TEST, so it does not model the real exit path (no save during the test); it passes on the branch although the leak above is real. Change: make it reproduce the case above (set a key without save, drop PYTEST_CURRENT_TEST, reset `_PYTEST_SEEN` via monkeypatch to its state before the test, then save) so it fails on the current branch code.
- packages/pymodaq_utils/src/pymodaq_utils/config.py:467 docstring "Once a pytest session has been seen (a test is running, now or earlier in this process, so the atexit save is covered too)": untrue until finding 1 is fixed (a session is only seen if save() ran during a test).

## API / behaviour (for the human, not blocking)
- New env var PYMODAQ_CONFIG_DIR changes the return of the public get_set_local_dir (signature unchanged; unset = old paths, verified in code and test).
- BaseConfig.save() under pytest (once seen) logs a warning and does not write unless config_path is inside PYMODAQ_CONFIG_DIR (also from __del__).
- get_set_local_dir is no longer a functools.cache wrapper: only `cache_clear` is kept; `cache_info`, `cache_parameters`, `__wrapped__` are gone (no use in packages/, plugins unverified; owner accepted, PR body must say so).
- Coverage before/after and test-count condition of decider-test-change: unverified by me (count goes up by 7).

summary: Adds a PYMODAQ_CONFIG_DIR override to get_set_local_dir and a pytest guard in BaseConfig.save that writes only inside the isolated folder; the stale-path case is fixed, but the atexit save still leaks test changes when no save() ran during a test, so it needs one more round.
