verdict: changes
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-M07 (branch agent/pymodaq_utils/docs/2026-11-19, commit 6f37e5c87)

## Task match
- Diff: 2 files, +27/-3, docstrings only (config.py Config.__call__, utils.py _literal_value). No code lines touched, no reformatting. In scope.

## Correctness of the claims (checked against dev_agent code)
- packages/pymodaq_utils/src/pymodaq_utils/config.py:550-571 Config.__call__ docstring: correct.
  - BaseConfig.__call__ (config.py:321-328) turns KeyError into ConfigError, so the `except KeyError` plural->singular fallback (config.py:573-576, 586-589, 599-602 on branch) never fires; "a missing plural key raises ConfigError" is true.
  - Singular branches: a scalar tries the plural, else returns `[entry]`; a list is returned as is: matches.
  - hdf5_backend branch calls super() twice with the same args, so a scalar is returned unwrapped and a list goes to the final super() call: "returned as found" is true.
  - Nit (no change needed): only the first matching key of the elif chain is handled; the docstring does not say this. Documenting the dead KeyError fallback is accurate, but it pins a latent bug in prose; a follow-up task to fix the fallback could be considered.
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:71-75 _literal_value docstring: the "Only ... are accepted. Anything else raises UnsafeExpressionError" claim is incomplete. Accepted by the code (utils.py:84-89, 118-121) and confirmed with safe_literal_eval on the installed package, but not listed:
  - `np.nan` / `numpy.nan` (only bare `nan`, `inf` are listed)
  - `np.True_`, `np.False_` (and the `numpy.` spellings)
  - the keywords `tzinfo=datetime.timezone.utc` and `fold=...` on constructors ("given plain arguments" implies no keywords)
  - Also worth saying: datetime, date, time are accepted only as `datetime.datetime`, `datetime.date`, `datetime.time` (bare `datetime(...)` raises UnsafeExpressionError, verified).
  - Constructor errors (e.g. `int('x')`) and unhashable set/dict keys raise ValueError/TypeError from _literal_value, not UnsafeExpressionError (safe_literal_eval wraps them, utils.py:202-203). The "anything else" phrase is about rejected content, so acceptable, but "raises UnsafeExpressionError" could say "rejected content raises".

## Required changes
1. utils.py:71-75: add `np.nan`, `np.True_`, `np.False_` (np./numpy. spellings) to the accepted constants, and state that the only keywords allowed on constructors are `tzinfo=datetime.timezone.utc` and `fold`; write the datetime constructors as `datetime.datetime`, `datetime.date`, `datetime.time`.

## Behaviour and API
- No name, signature, default, return value or exception changes. Docstrings only.

## Tests
- Docs-only change: no test required (fails_without_fix n/a).
- Branch snapshot (git archive, PYTHONPATH on the branch src, Python 3.14 env): packages/pymodaq_utils tests 306 passed, 3 skipped, 1 failed (tests/config_test.py::test_nested_update_from_user, pre-existing on dev_agent as the caller noted).
- flake8 blocking selection: 0. No new line over 120 chars (only pre-existing config.py:285, 472).
- Worktree left as found (untracked files present belong to other reviews, not this one).

summary: Adds an accurate docstring to Config.__call__ and extends the _literal_value docstring, which still omits a few accepted forms (np.nan, np.True_/np.False_, tzinfo/fold keywords) and needs that completed.
