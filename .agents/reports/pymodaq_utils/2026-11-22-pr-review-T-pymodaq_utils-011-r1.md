verdict: changes
public_api: yes
behaviour_change: yes
fails_without_fix: n/a

# PR review r1: T-pymodaq_utils-011 (packages.get_entrypoints delegates to utils.get_entrypoints)
branch: agent/pymodaq_utils/refactor/2026-11-22-packages-get-entrypoints, head f52dc7712, one commit, Agent-Run trailer present.
merge_gate lint: LINT OK (23 changed lines, product files only, trailers present). Caller reports lint, layering, pyqt6/pyside6 tests green.

## 1. Task match
- Only packages.py:159-185 changes, as the task asks. Delegation is packages -> utils, never the reverse, with a function-local
  import. Both public names kept. Monkeypatch tests untouched. In scope.

## 2. Correctness
- Delegation is right. utils.get_entrypoints has the same lookup chain as the old body and always returns a list.
- No in-repo caller uses packages.get_entrypoints (grep over packages/): every caller imports from pymodaq_utils.utils. The
  EntryPoints-only features (.names, .select) are therefore unused here. External plugins: unverified.
- deprecation_msg(stacklevel=3) is called from the function, so the warning points at the caller of
  packages.get_entrypoints. Correct. pyproject filterwarnings ignore DeprecationWarning, so the suite stays quiet.

## 3. Behaviour and API
- Public name packages.get_entrypoints: return type EntryPoints -> list, and a new DeprecationWarning on every call.
  Decider-compat-risk approved this in the plan. public_api: yes means the PR goes to the human.

## 4. Tests
- No test added or changed. The new behaviour (returns a list, emits DeprecationWarning, delegates to utils) is unpinned.
  Add a test in packages/pymodaq_utils/tests (for example packages_test.py), asserting:
  a) `isinstance(result, list)` and equality with `utils.get_entrypoints(group)` for a real group (e.g. 'pymodaq.plugins');
  b) `pytest.warns(DeprecationWarning, match='pymodaq_utils.utils.get_entrypoints')`.
  Write it so it does not depend on installed plugins.

## 5. Docs and docstrings
- packages.py:173-175: `.. deprecated::` has no version argument. Sphinx requires one ("1 argument(s) required"), and the
  repo style is `.. deprecated:: 5.3.5` (plugin_checks.py:4). Add the version in which this lands.
- packages.py:2: `from importlib import metadata` is now unused in this module (no other `metadata.` use). Remove it, or
  keep it on purpose and say so, since `from pymodaq_utils.packages import metadata` would otherwise break. Ruff F401 may fire.
- Return-type change is stated in docstring and commit message, as required.

## Required changes
1. Add the test described in section 4.
2. Give `.. deprecated::` a version.
3. Remove or justify the unused `metadata` import.

summary: packages.get_entrypoints now delegates to pymodaq_utils.utils.get_entrypoints, so it returns a list instead of EntryPoints and emits a DeprecationWarning; no in-repo caller used the old return type.
