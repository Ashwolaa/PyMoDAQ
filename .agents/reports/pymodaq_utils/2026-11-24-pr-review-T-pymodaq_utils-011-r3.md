verdict: approve
public_api: yes
behaviour_change: yes
fails_without_fix: n/a

# PR review r3: T-pymodaq_utils-011 (packages.get_entrypoints delegates to utils.get_entrypoints)
branch: agent/pymodaq_utils/refactor/2026-11-22-packages-get-entrypoints, two commits (242163c17, fe4f8158d), both with Agent-Run trailer.
merge_gate lint: LINT OK (35 changed lines, product files only, trailers present). Caller reports static + pyqt6/pyside6 green on the rebased head (I did not re-run the branch suite).

## r2 findings
1. Missing test: FIXED. packages/pymodaq_utils/tests/packages_test.py:29-34 asserts DeprecationWarning (match 'pymodaq_utils.utils.get_entrypoints'), `isinstance(result, list)` and equality with utils.get_entrypoints. Run against dev_agent code it fails (1 failed, 4 passed: no warning raised), so it pins the new behaviour. Temp file removed, git status clean.
2. `.. deprecated::` without version: FIXED. packages.py:173 `.. deprecated:: 5.4.0`; latest tag is 5.4.0a0, so 5.4.0 is the next release.
3. Unused `from importlib import metadata`: FIXED. Removed at packages.py:2. Grep over packages/ finds no `from pymodaq_utils.packages import metadata` or `packages.metadata` user.

## 1. Task match
- Only packages.get_entrypoints and its test change. packages -> utils delegation with function-local import, both public names kept, the three monkeypatch tests untouched. No drift, no reformatting of untouched lines.

## 2. Correctness
- utils.get_entrypoints (utils.py:759-783) has the same lookup chain and always returns a list. The delegation is correct.
- No in-repo caller of packages.get_entrypoints (grep over packages/). External plugins: unverified.
- deprecation_msg (warnings.py:8) raises DeprecationWarning with stacklevel=3, so the warning points at the caller of packages.get_entrypoints.

## 3. Behaviour and API
- Public packages.get_entrypoints: return type EntryPoints -> list, plus a DeprecationWarning on every call. decider-compat-risk approved this in the plan. public_api: yes, so the PR goes to the human.

## 4. Tests
- The test uses a group that does not exist, so the equality check compares [] with []. The isinstance check and the warning check still separate old and new behaviour. This is a minor weakness and does not block.

## 5. Docs
- The docstring Returns section ("list of importlib.metadata.EntryPoint") and the deprecated note (no `.names`/`.select()`) match the code.

summary: packages.get_entrypoints now delegates to pymodaq_utils.utils.get_entrypoints, so it returns a list instead of EntryPoints and emits a DeprecationWarning (deprecated 5.4.0); a new test pins this, and no in-repo caller used the old return type.
