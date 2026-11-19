verdict: approve
public_api: yes
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-M05 (branch agent/pymodaq_utils/refactor-mutable-defaults/2026-11-19, commit cfc5ee21e)

## Task match
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:444,458,476: `paths=[]` -> `paths=None` plus `if paths is None: paths = []` in the three recursive_find_* functions, as the plan asks.
- utils.py:445-446,461-462,479-482: the stale "pass a new list" docstring sentences are removed, as the plan asks.
- `filters=[...]` list defaults left untouched (read-only, plan note says they were dropped); no other lines touched. Diff is 59+/9-, under the 300-line cap.

## Correctness
- Recursive calls (utils.py:454,467,488) still pass `paths` explicitly, so accumulation within one call is unchanged.
- An explicit list is still appended to in place and returned (checked by test_*_appends_to_given_list).
- Callers: grep over packages/ finds only the recursive calls, the `__main__` block (utils.py:934, explicit-free call) and tests/utils_test.py:209-220; none relied on cross-call accumulation.
- flake8 E9/F63/F7/F82 on packages/pymodaq_utils: 0.

## Behaviour and API
- utils.py:444,458,476: public signatures change their `paths` default from `[]` to `None`. Every call that passed a list or nothing keeps working; the only observable change is that successive default calls no longer return results from earlier calls (the bug). Hard rule 1 not violated: no name removed or renamed. Flagged public_api: yes because a public default changed (B2 deferred this task for the same reason).
- No new exceptions or warnings.

## Tests
- tests/utils_test.py:404-449: six new tmp_path tests. Ran the branch test file against dev_agent code: test_extension_not_polluted, test_files_not_polluted, test_expr_not_polluted FAIL (results polluted by earlier calls); the three *_appends_to_given_list tests pass (behaviour preserved). Temp file deleted, git status clean.
- Full scope suite on a git-archive snapshot of the branch: 312 passed, 3 skipped, 1 failed (tests/config_test.py::test_nested_update_from_user, pre-existing on dev_agent per caller).
- Assertions are exact lists, except tests/utils_test.py:449 (`len(given) == 3`), which is weaker; nit, not blocking.
- Qt matrix not relevant (no Qt code touched); not run.

## Docs
- Remaining docstrings match the code (filters skipping, `[file path, line index, line]` entries, replace behaviour) — verified by reading utils.py:444-505 on the branch.
- Nit: utils.py:445-446 the one-line docstring now closes on its own line; cosmetic.

summary: Replace the shared mutable `paths=[]` default of the three recursive_find_* helpers with `None`, so repeated calls no longer return results from earlier calls, with tests that fail on the old code.
