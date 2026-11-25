verdict: changes
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-014 r2 (run 2026-11-25-merge-T-pymodaq_utils-014-r2)

Branch: agent/pymodaq_utils/test-quality/2026-11-25, commits bb6fd193f + 0f9471c22, one new file
`packages/pymodaq_utils/tests/package_import_test.py` (+29 lines). No source change.

## r1 findings
- r1 #3 (`assert reloaded is pymodaq_utils` vacuous): fixed, the line is gone.
- r1 #1 (CONFIG assertion can never fail): still open. `monkeypatch.delattr(pymodaq_utils, 'CONFIG')` was added, but
  `assert pymodaq_utils.CONFIG is GlobalConfig()` runs after the `finally: importlib.reload(pymodaq_utils)`, and that
  unpatched reload always recreates CONFIG (`__init__.py:47`). Verified by a mutant test: CONFIG deleted again right
  after the patched reload (as if the import had stopped before line 47); the test still passed (2 passed).
- r1 #2 (comment claims a check not made): still open, same cause (line 28).

## Checks
1. Task match / drift: in scope, test only, uses capsys + `isolated_config_dir`, patches `set_logger` on the logger
   module and restores via reload in `finally`, as the plan asks. `merge_gate.py lint`: LINT OK (29 lines, trailers present).
2. Correctness: patch target right (`__init__.py:24` re-imports `set_logger` on reload). `GlobalConfig` is a Singleton
   (config.py:504, singleton.py:14-18), so `CONFIG` is the same instance everywhere; monkeypatch teardown re-sets the
   original attribute, which is the same object. No leak to other tests seen.
3. Behaviour / API: none changed.
4. Tests: no fix, so n/a. Test passes against dev_agent code; the two output assertions are meaningful (an
   `except Exception` path prints "Couldn't create the local folder...", not "msg"; checked by reading). The CONFIG
   assertion is not (see findings). Temp file removed, `git status` clean.
5. Docs: docstring accurate; comment at line 28 not.

## Findings (what to change)
- packages/pymodaq_utils/tests/package_import_test.py:29: the CONFIG check runs after the restoring reload, so it is
  always true. Fix: inside the `try`, right after the patched `importlib.reload(...)` (before `finally`), record
  `config_after = getattr(pymodaq_utils, 'CONFIG', None)`; after the block assert `config_after is GlobalConfig()`.
- packages/pymodaq_utils/tests/package_import_test.py:28: comment "CONFIG, defined after it, was recreated" is
  only true once the line above checks the value captured before the restore.

summary: Adds a test that a ConfigError raised while creating the pymodaq logger is printed and does not stop the pymodaq_utils import; the CONFIG check must read the attribute before the restoring reload, or it can never fail.
