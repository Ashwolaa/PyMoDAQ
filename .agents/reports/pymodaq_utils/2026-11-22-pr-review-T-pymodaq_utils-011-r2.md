verdict: changes
public_api: yes
behaviour_change: yes
fails_without_fix: n/a

# PR review r2: T-pymodaq_utils-011 (packages.get_entrypoints delegates to utils.get_entrypoints)
branch: agent/pymodaq_utils/refactor/2026-11-22-packages-get-entrypoints, head be45c4198 (rebased), one commit, Agent-Run trailer present.
merge_gate lint: LINT OK (23 changed lines, product files only, trailers present). Caller reports static + pyqt6/pyside6 green.
The diff is the same as at r1 (only packages.py, 13+/10-): the rebase applied none of the r1 required changes.

## r1 findings
1. Missing test for the new behaviour: STILL OPEN. No file under packages/pymodaq_utils/tests changes; no test references
   get_entrypoints in packages/pymodaq_utils/tests.
2. `.. deprecated::` without version: STILL OPEN (packages.py:174).
3. Unused module import `from importlib import metadata`: STILL OPEN (packages.py:2; the only other uses are the local
   variable `metadata` in get_metadata_from_json, line 89, and docstring text, line 172).

## 1. Task match
- In scope: only packages.py get_entrypoints changes, delegation packages -> utils with function-local import, both public
  names kept, monkeypatch tests untouched. No drift.

## 2. Correctness
- utils.get_entrypoints (utils.py:762-785) has the same lookup chain and always returns a list. Delegation correct.
- No in-repo caller of packages.get_entrypoints (grep over packages/ finds none). External plugins: unverified.
- deprecation_msg default stacklevel=3 (warnings.py:7) points the warning at the caller. Correct.

## 3. Behaviour and API
- Public packages.get_entrypoints: return type EntryPoints -> list and a new DeprecationWarning per call. Approved by
  decider-compat-risk in the plan; public_api: yes sends the PR to the human.

## 4. Tests
- packages/pymodaq_utils/tests: no test pins the new behaviour. Behaviour change, not a bug fix, so fails_without_fix n/a.

## Required changes
1. Add a test in packages/pymodaq_utils/tests (e.g. packages_test.py) asserting, without depending on installed plugins:
   a) result of packages.get_entrypoints(group) `isinstance(..., list)` and `== utils.get_entrypoints(group)`;
   b) `pytest.warns(DeprecationWarning, match='pymodaq_utils.utils.get_entrypoints')`.
2. packages.py:174: write `.. deprecated:: <version this lands in>` (repo style: plugin_checks.py:4 `.. deprecated:: 5.3.5`).
3. packages.py:2: remove `from importlib import metadata`, or keep it with a comment stating it is kept for
   `from pymodaq_utils.packages import metadata` compatibility.

summary: packages.get_entrypoints now delegates to pymodaq_utils.utils.get_entrypoints, so it returns a list instead of EntryPoints and emits a DeprecationWarning; no in-repo caller used the old return type.
