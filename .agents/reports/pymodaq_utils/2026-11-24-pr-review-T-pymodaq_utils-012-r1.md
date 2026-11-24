verdict: changes
public_api: yes
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-012 r1 (run 2026-11-24-merge-T-pymodaq_utils-012-r1)
Branch: agent/pymodaq_utils/refactor/2026-11-24-pymodaq-config-dir (1 commit, 3f4c56301, 68+/6-)

## Checks done
- Task match: the diff touches only the cited files (config.py get_set_local_dir + save, config_test.py new tests). The cache key includes the env var, `cache_clear` is kept. No reconcile/schema work, no conftest. No drift seen.
- `merge_gate.py lint`: LINT OK (74 changed lines, product files only, trailers present).
- Branch tests run against dev_agent code (tmp copy, throwaway HOME, removed after, `git status` clean): 3 of the 5 new tests fail without the change
  (test_env_var_sets_system_and_user_dirs, test_cache_key_includes_env_var, test_save_skipped_under_pytest); test_unset_keeps_default_paths
  and test_save_allowed_with_isolated_dir pass there, as expected for regression checks.
- Callers: get_set_local_dir is used across pymodaq_gui/pymodaq (config.py, tests, launcher conftest); with the variable unset the paths are unchanged (verified in code).
  No use of `cache_info` / `__wrapped__` in packages/ (grep); plugins unverified.
- ConfigSaverLoader (pymodaq_gui/config_saver_loader.py:88) reloads from memory, so the skipped save does not break its tests (verified in code; the suite was not run by me).
- Coverage before/after and test count condition of decider-test-change: unverified by me (count goes up by 5).

## Findings
- packages/pymodaq_utils/src/pymodaq_utils/config.py:459 guard misses the main write path: BaseConfig.__init__ registers `atexit.register(self.save)` (config.py:339) and pytest deletes PYTEST_CURRENT_TEST after each test (_pytest/runner.py:200), so at interpreter exit save() writes every in-memory change made by tests to the real user file. Verified with a branch-code experiment: a test that does `cfg['k'] = 42; cfg.save()` leaves `k = 42` in $HOME/.pymodaq/config/ after the session. Same gap for saves during collection. Change: make the guard detect a pytest session, not only a running test (for example `'pytest' in sys.modules`, or decide once in __init__ and keep it on the instance), and add a test for the atexit path.
- packages/pymodaq_utils/src/pymodaq_utils/config.py:459 `PYMODAQ_CONFIG_DIR` set lets the write through even when `config_path` (cached_property, config.py:415) was resolved before the variable was set: the write then goes to the real ~/.pymodaq file. Verified: access config_path, monkeypatch.setenv, save() -> `stale = 1` written to $HOME/.pymodaq/config/. Change: allow the write only if `self.config_path` is inside `PYMODAQ_CONFIG_DIR` (`Path.is_relative_to`), else warn and return; add a test.
- packages/pymodaq_utils/tests/config_test.py:368 assigns `config._modified_config` directly on the CustomConfig0 singleton and never restores it, so the atexit save (finding 1) writes `{'guard_test': 1}` over that user file after the run. Change: use `monkeypatch.setattr` as in test_save_allowed_with_isolated_dir.
- packages/pymodaq_utils/tests/config_test.py:345 the `or` assertion accepts any folder named `.pymodaq`. Change: assert `== CONFIG_BASE_PATH / '.pymodaq'` or the home fallback exactly.
- packages/pymodaq_utils/tests/config_test.py:359 `!= first` is not an exact result, and the cache_clear at :360 is skipped when the assertion fails. Change: assert `== tmp_path / 'b' / 'user'`; clear the cache in a fixture/finalizer.
- packages/pymodaq_utils/src/pymodaq_utils/config.py:456 the docstring says the user file is not written under pytest; untrue until finding 1 is fixed.

## API / behaviour (for the human, not blocking)
- New public knob: env var PYMODAQ_CONFIG_DIR changes the return of the public get_set_local_dir (signature unchanged, unset = old paths).
- BaseConfig.save() under pytest now logs a warning and does not write (also from __del__, so one warning per collected config).
- get_set_local_dir is no longer a functools.cache wrapper: only `cache_clear` is kept; `cache_info`, `cache_parameters`, `__wrapped__` are gone (no use in packages/, plugins unverified).

summary: Adds a PYMODAQ_CONFIG_DIR override to get_set_local_dir and a pytest guard in BaseConfig.save; the guard still lets the atexit save and stale cached paths write the real user config, so it needs another round.
