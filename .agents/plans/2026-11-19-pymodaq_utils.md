# Plan: pymodaq_utils — 2026-11-19
base commit: 1aba4217b   mode: run (refreshed 2026-11-19 after T-001 execution; scan identical to original, no re-deliberation needed)

Scanners used (venv ~/.venvs/optimize-agents, jscpd via ~/.npm-global): ruff (196 findings), vulture, radon, jscpd (1.81% dup).
Rebase T2/T3 onto dev_agent after #3 merges (both touch config.py/environment.py).
Merge order (arbiter, binding): T2, T3, T5, T4, T1. All five stay separate PRs; hunks are far apart, rebases are clean.
Before each merge: pytest from packages/pymodaq_utils, flake8 blocking set, layering_test, on the rebased branch.

## T-pymodaq_utils-001 (T2) Remove unused imports
- scope: pymodaq_utils   specialty: hygiene   risk: low
- files: config.py:3,11,13,23; environment.py:3 and lambda `l` 193-194; mysocket.py:8; serialize/mysocket.py:1 (TYPE_CHECKING optional); math_utils.py:7 (duplicate Union)
- note: drops the unused pymodaq_gui TYPE_CHECKING import (config.py:23), helps layering. Edit only those lines; do not re-sort.
- verdicts: decider-compat-risk: approve — no importer of these names under packages/ and docs/; decider-triage: approve — each name only on its import line
- also: obsolete layering_test ALLOWED entry for config.py removed (decider-test-change: approve)
- status: executed — draft PR Ashwolaa/PyMoDAQ#3 -> dev_agent, awaiting human review

## T-pymodaq_utils-002 (T3) Exception handling
- scope: pymodaq_utils   specialty: hygiene   risk: low
- files: config.py:118 (drop unused `e`), config.py:325-326 (keep `as e`, add `from e`), environment.py:153, packages.py:96 (bare except -> except Exception)
- note: keep separate from T2; only changes KeyboardInterrupt/SystemExit handling and traceback chaining. Optional test: __cause__ is KeyError.
- verdicts: decider-compat-risk: approve — try bodies only raise Exception subclasses, ConfigError unchanged; decider-triage: approve — spec corrected (do not drop `e` at 325)
- status: approved

## T-pymodaq_utils-003 (T5) Docstrings
- scope: pymodaq_utils   specialty: docs   risk: low
- files: config.py:549 Config.__call__ (new docstring), utils.py:68-75 _literal_value (extend)
- text constraints (from both deciders): Config.__call__ covers backend/backends, debug_level/debug_levels, dynamic/dynamics; plural falls back to singular on KeyError; singular returns the stored list, else the plural key's value, else the singular value wrapped in a list; NO hdf5_backend sentence (it falls under "any other key", forwarded unchanged). _literal_value: add nan/inf, np/numpy.nan, np/numpy.True_/False_, array(...)/np.array(...)/numpy.array(...), tzinfo=datetime.timezone.utc and fold keywords of the safe constructors, raises UnsafeExpressionError otherwise. Docstrings only; leave config.py:554 indentation and :601 whitespace.
- dropped from original T5: check_extension_source docstring (already accurate)
- verdicts: decider-compat-risk: approve (round 2); decider-triage: approve (round 2, after veto on text-less original)
- status: approved

## T-pymodaq_utils-004 (T4) Fix no-op in extract_authors_from_description
- scope: pymodaq_utils   specialty: refactor (bugfix)   risk: medium
- files: packages.py:207 (`posi == posa + 50` -> `posi = len(description)` when no Instruments marker), new tests
- tests: no Instruments + Contributors; no Instruments + no Contributors; last author's final char kept; each asserts the exact list, short authors, no truncation asserted
- note: public name, no in-repo callers; pymodaq_plugin_manager has its own copy (validate.py:326,392, unverified here). Label as bug fix.
- verdicts: decider-compat-risk: approve (round 2; first fix posi=posa+50 vetoed: truncates names); decider-test-change: approve — tests only added, fail on old code
- status: proposed (touches tests, public function)

## T-pymodaq_utils-005 (T1) Shared mutable defaults
- scope: pymodaq_utils   specialty: hygiene (bugfix)   risk: low
- files: utils.py:444,458,475 (paths=None + in-body default); docstring notes at 447,463,482-483 removed; tests/utils_test.py new test
- tests: tmp_path with known files; second call returns same as first (equal lists); replace stays False; filters=[...] left alone
- verdicts: decider-compat-risk: approve — only recursive/__main__ callers, keyword paths preserved; decider-test-change: approve — test only added
- status: proposed (touches tests)

## Dropped (triage)
read-only list defaults (utils.py:459,476,511, array_manipulation.py:151, math_utils.py:616); abstract.py:12 abstractmethod (public module); false positives: __init__.py:15, serialize/factory.py:3, serializer.py:3, safe_pickle.py:53 pid, serializer_legacy.py:13; repo-wide autofix (hard rule 5); jscpd duplication (1.81%, likely intentional).

## Needs a separate staged plan (not a task yet)
Complexity refactors with characterisation tests first, one function per PR: rules.py:685 check_extension_source F(65) (keep rule ids/messages), utils.py:68 _literal_value F(42), rules.py:490 check_plugin_source E(38). Lint config note: ruff reports 196 findings, mostly UP006/I001/UP035/whitespace in files no task touches.

## Blocked
- packages/pymodaq_utils/tests/config_test.py::test_nested_update_from_user fails on dev_agent (pre-existing, unrelated to any task): needs the human or its own task.
- PyQt6 not yet run for the T-001 checks (PySide6 only).
