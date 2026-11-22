verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-M11 r1 (run 2026-11-22-merge-T-pymodaq_utils-M11-r1)
Branch: agent/pymodaq_utils/refactor/2026-11-22-shared-input-checks (2 commits: pinning tests 75ae07593, then refactor d545410d9).

## 1. Task match and drift
- `merge_gate.py lint`: LINT OK, 122 changed lines, product files only, trailers present.
- Diff touches only math_utils.py ft/ift/ft2/ift2 checks (task: math_utils.py:374-478) and math_utils_test.py; pinning tests were committed first, as the test-change verdict required.
- packages/pymodaq_utils/tests/math_utils_test.py:202: a whitespace-only line (trailing spaces) became an empty line at the insertion point; it is the boundary line of the new block, so I am not counting it as drift. No other untouched lines changed.

## 2. Correctness (verified by reading old and new code)
- math_utils.py:374 `_check_ft_input`: same checks in the same order as the old ft/ift code (dim type -> TypeError, then asserting x is an ndarray and -1 <= dim <= ndim-1), same message.
- math_utils.py:383 `_check_ft2_input`: the old scalar and iterable branches merge into `dims = dim if hasattr(dim,'__iter__') else (dim,)`: same TypeError message, same `d <= len(x.shape)` assert, ndarray assert still first. A str dim still iterates over its characters and raises TypeError, as before. A generator dim is consumed the same way as before.
- Callers: pymodaq_data/data.py:2750,2794 (ft/ift with int axis) see no change. pymodaq/utils/math_utils.py star-imports the module, and the new `_`-prefixed helpers are not exported by `*`.

## 3. Behaviour and API
- No public name, signature, default, return value or exception changed. Two private helpers were added.

## 4. Tests
- The branch's math_utils_test.py, copied as math_utils_review_tmp_test.py and run against dev_agent code: 40 passed. A refactor's pinning tests should pass without the change, so fails_without_fix is n/a. Temp file deleted, git status clean.
- Same test file against the branch code (git archive into a tmp dir, PYTHONPATH confirmed to that src): 40 passed.
- The tests check exact results: they match error messages, compare outputs to numpy references with allclose, and pin the check order and the "too small dim is left to numpy" edge case.
- Qt backends not relevant (no Qt code). Full pymodaq_utils suite not re-run here: unverified beyond math_utils_test.py.

## 5. Docs and docstrings
- The helper docstrings ("Shared input checks of ft and ift", "...dim is an integer or an iterable of integers") match the code. Public docstrings are unchanged.

summary: Moves the duplicated input checks of ft/ift and ft2/ift2 into two private helpers without changing behaviour, after first adding tests that pin the error types, messages, check order and results.
