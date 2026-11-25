verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-014 r3 (run 2026-11-25-merge-T-pymodaq_utils-014-r3)

Branch: agent/pymodaq_utils/test-quality/2026-11-25, commits fecc6ea77, 89e15bd27, 8ed5f4e17. One new file:
`packages/pymodaq_utils/tests/package_import_test.py` (+32 lines). No source change.

## r2 findings
- r2 #1 (CONFIG check runs after the restoring reload, so it is always true): fixed. Line 24 now reads
  `config_after = getattr(pymodaq_utils, 'CONFIG', None)` inside the `try`, before the `finally` reload, and line 32
  asserts `config_after is GlobalConfig()`. Checked with a mutant: `del pymodaq_utils.CONFIG` added right after the
  patched reload makes the test fail (1 failed); the unchanged test passes (1 passed), both run against dev_agent code.
- r2 #2 (comment at line 28 claimed a check that was not made): fixed. Lines 30-31 now say CONFIG was recreated
  "by the patched reload itself", and that is what is now checked.

## Checks
1. Task match / drift: matches the task notes (patches `set_logger` to raise `ConfigError("msg")`, reloads, restores
   with a reload in `finally`, uses capsys and `isolated_config_dir` from conftest.py:7). Test only, no other files.
   `merge_gate.py lint`: LINT OK (32 changed lines, product files only, trailers present).
2. Correctness: the patch target is right, because `__init__.py:24` re-imports `set_logger` from the logger module on
   each reload. The handler at `__init__.py:40-41` prints the message; the `except Exception` branch at :42-43 would print
   "Couldn't create the local folder", and the test asserts that text is absent. `GlobalConfig` is a singleton, so
   identity with `GlobalConfig()` holds. monkeypatch puts the original CONFIG back on teardown (same instance).
3. Behaviour / API: none changed.
4. Tests: not a bug fix, so n/a. Assertions are exact (the message is in the output, the other branch's text is not,
   CONFIG is the same object). Temp files were removed and `git status` is clean.
5. Docs: the docstring and comments match what the code does.

## Notes (not findings)
- At interpreter exit a "Logging error ... I/O operation on closed file" is printed. dev_agent's own `config_test.py`
  prints it too when run alone, so this branch did not cause it.

summary: Adds a test that a ConfigError raised while creating the pymodaq logger is printed, the other error branch is not taken, and the pymodaq_utils import still goes on to create CONFIG.
