verdict: changes
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-014 r1 (run 2026-11-25-merge-T-pymodaq_utils-014-r1)

Branch: agent/pymodaq_utils/test-quality/2026-11-25, one commit a46db53e7, one new file (+29 lines).

## Checks
1. Task match / drift: in scope. The only file is the new test `packages/pymodaq_utils/tests/package_import_test.py`. No source change. It patches `pymodaq_utils.logger.set_logger`, reloads the package, restores it in `finally`, uses capsys and `isolated_config_dir`, as the plan asks. `merge_gate.py lint`: LINT OK (29 changed lines, trailers present).
2. Correctness: patching `set_logger` on `pymodaq_utils.logger` is right, because `__init__.py:24` re-runs `from pymodaq_utils.logger import set_logger` on reload. The `finally` reload rebinds the real function. `set_logger` adds a handler only `if add_handler and not logger.handlers` (logger.py:49), so the restore adds no duplicate handler. `GlobalConfig` is a Singleton and `pymodaq_utils.config` is not reloaded, so `CONFIG` stays the same instance and no tmp path leaks to later tests (verified in config.py:504-515).
3. Behaviour / API: test only, no public name touched.
4. Tests: there is no fix (the handler was already merged by T-007), so fails_without_fix is n/a. The new test passes against dev_agent code (1 passed). It also passes together with config_test.py and logger_test.py (40 passed), and the git status is clean afterwards. Removing the `except ConfigError` clause would send the error to `except Exception`, which prints "Couldn't create the local folder..." and not "msg", so both output assertions would fail. This was checked by reading the code, not by running the mutation.
   The "--- Logging error ---" at exit also happens without this test (config_test.py + logger_test.py alone): it is not caused by this branch.
5. Docs / docstrings: the docstring is accurate. The comment at line 28 is not (see findings).

## Findings (what to change)
- packages/pymodaq_utils/tests/package_import_test.py:29: `assert hasattr(pymodaq_utils, 'CONFIG')` can never fail. `importlib.reload` reuses the module `__dict__`, so `CONFIG` from the first import survives even if the reload stopped before line 47. Fix: call `monkeypatch.delattr(pymodaq_utils, 'CONFIG')` (add the `monkeypatch` fixture) before the patched reload, and assert `pymodaq_utils.CONFIG is GlobalConfig()` after it.
- packages/pymodaq_utils/tests/package_import_test.py:28: the comment "the names defined after it exist" claims a check the current assertion does not make. Keep it only once the line above is fixed.
- packages/pymodaq_utils/tests/package_import_test.py:25: `assert reloaded is pymodaq_utils` is always true for `importlib.reload` and tests nothing. Drop it, or replace it with the CONFIG check above.

summary: Adds a test that a ConfigError raised while creating the pymodaq logger is printed and does not stop the pymodaq_utils import; its CONFIG assertion must be made non-vacuous (delete the attribute before the reload).
