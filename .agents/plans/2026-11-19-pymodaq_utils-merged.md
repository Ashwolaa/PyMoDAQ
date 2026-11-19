# Plan: pymodaq_utils — 2026-11-19 (merged)
base commit: bde8dbd11   source tree: 4a0d17e7dcfc (unchanged since the scans)   mode: run
Merged by the human-side session from 8 plans on identical source: pilot, expA, A2-sonnet, A2-haiku, A3-sonnet,
A3-haiku, B1, B2 (all in this folder). "found" = how many of the 8 runs proposed it. Status rule: `approved` only if
no run vetoed or blocked it and it touches neither tests nor public API; otherwise `proposed` for the human.
Re-check every file:line against HEAD before executing (plans expire after 14 days).

Already done: unused imports (found 8/8) -> draft PR Ashwolaa/PyMoDAQ#3 (also drops the obsolete layering allowlist entry).
Merge order (packages.py and config.py are shared): M04 first, then M01; M02 and M05 both edit utils.py, run M02 first.

## T-pymodaq_utils-M01 Fix the no-op comparison in extract_authors_from_description
- scope: pymodaq_utils   specialty: refactor (bug fix)   risk: medium   found: 7/8
- files: packages.py:207 (`posi == posa + 50` -> `posi = len(description)` when no "Instruments" marker); new tests in packages/pymodaq_utils/tests/
- tests: characterisation first; cases: no Instruments + Contributors, no Instruments + no Contributors, last author's final character kept; assert exact lists
- note: today `posi` stays -1, so `description[posa:-1]` drops the last character. `posi = posa + 50` was vetoed in 4 runs (cuts long author lists). pymodaq_plugin_manager has its own copy (validate.py, unverified).
- verdicts: decider-compat-risk: approve with the len(description) fix (pilot r2, A2-sonnet r2, A3-sonnet, A3-haiku, B1, B2); decider-test-change: approve, tests only added (pilot, A3-*, B1, B2); A2-haiku: blocked, "owner decides intent"
- status: done — draft PR #5, CI green (2026-11-19)

## T-pymodaq_utils-M02 ThreadCommand loses the deprecated `attributes=` value
- scope: pymodaq_utils   specialty: refactor (bug fix)   risk: low   found: 2/8
- files: utils.py:365-369 (line 369 `self.attribute = attribute` overwrites the value set from `attributes`; make it the `else` branch); new test in tests/utils_test.py expecting the deprecation warning
- verdicts: decider-compat-risk: approve, restores the documented deprecation path, no in-repo caller passes attributes= (A2-haiku, B1); decider-test-change: approve, test only added (A2-haiku, B1)
- status: done — draft PR #6, CI green (2026-11-19)

## T-pymodaq_utils-M03 check_received_length spins forever when the peer closes
- scope: pymodaq_utils   specialty: refactor (bug fix)   risk: medium   found: 1/8
- files: mysocket.py:85-91 (`recv` returns b'' on a closed peer, so `mess_length` never grows): raise ConnectionError on an empty read; new fake-socket test
- note: serialize/mysocket.py:29 has its own check_received_length over an in-memory bytes string, not affected (verified).
- verdicts: decider-compat-risk: approve, ConnectionError is an OSError subclass and only the closed-peer path changes (B1); decider-test-change: approve in round 2, test only added (B1)
- status: done — draft PR #7, CI green (2026-11-19)

## T-pymodaq_utils-M04 Exception hygiene
- scope: pymodaq_utils   specialty: hygiene   risk: low   found: 8/8
- files: environment.py:153 and packages.py:96 (`except:` -> `except Exception:`); config.py:118 (drop unused `e`); config.py:325-326 (keep `as e`, add `raise ... from e`)
- verdicts: approved in all 8 runs (compat-risk and a second decisioner each time); the only correction, made in 3 runs: do not drop `e` at :325
- status: done — draft PR #4, CI green (2026-11-19)

## T-pymodaq_utils-M05 Shared mutable `paths=[]` default in recursive_find_*
- scope: pymodaq_utils   specialty: refactor (bug fix)   risk: low   found: 7/8
- files: utils.py:444,458,475 (`paths=None`, `if paths is None: paths = []`, recursive calls keep passing paths); remove the stale docstring warnings at ~447,463,482; new tmp_path test in tests/utils_test.py
- note: only `paths` accumulates; the read-only list defaults (utils.py:459,476,511, array_manipulation.py:151, math_utils.py:616) were dropped by most runs.
- verdicts: decider-compat-risk: approve in 7 runs; decider-test-change: approve, test only added; B1 approved it outright, B2 deferred it (public signature); every Opus run kept it proposed
- status: done — draft PR #8, CI green (2026-11-19)

## T-pymodaq_utils-M06 Moved plugin_tools shims never call deprecation_msg
- scope: pymodaq_utils (+ packages/pymodaq/pyproject.toml)   specialty: refactor (compat)   risk: medium   found: 2/8
- files: plugin_checks.py, plugin_rules.py, plugin_scaffold.py (docstrings say deprecated in 5.3.5, no warning is emitted; verified); call deprecation_msg before the sys.modules swap; packages/pymodaq/pyproject.toml:76 (point check_plugin at plugin_tools.checks:main); regenerate legacy_to_current.rst with docs/legacy_to_current.py, never by hand; new warning test
- verdicts: decider-compat-risk: approve, closes the hard-rule-1 gap (A2-haiku, B2); decider-triage / test-change: approve with conditions (A2-haiku, B2)
- status: proposed (public API, touches tests, leaves the scope)

## T-pymodaq_utils-M07 Docstrings for Config.__call__ and _literal_value
- scope: pymodaq_utils   specialty: docs   risk: low   found: 1/8
- files: config.py:549 (new docstring: backend(s), debug_level(s), dynamic(s) singular/plural fallback, any other key forwarded), utils.py:68-75 (_literal_value: list the accepted constants and constructors, raises UnsafeExpressionError otherwise). Docstrings only.
- verdicts: decider-compat-risk and decider-triage: approve in round 2 (pilot)
- status: approved

## T-pymodaq_utils-M08 API doc pages for config, logger, enums and plugin_tools
- scope: pymodaq_utils   specialty: docs   risk: low   found: 1/8
- files: new .rst under docs/src/api/utility_api/ (existing automodule pages there: mathematical, units_conversion, utility_classes; none for config, logger, enums or plugin_tools, verified); never edit legacy_to_current.rst
- verdicts: decider-compat-risk and decider-triage: approve (A2-sonnet, two tasks merged here)
- status: approved

## T-pymodaq_utils-M09 Module docstring on import side effects
- scope: pymodaq_utils   specialty: docs   risk: low   found: 1/8
- files: __init__.py (module docstring: what importing pymodaq_utils does, e.g. serializable registration and CONFIG)
- verdicts: decider-compat-risk: approve, claim verified in code; decider-triage: approve (B2)
- status: approved

## T-pymodaq_utils-M10 Release note for the plugin_tools move
- scope: pymodaq_utils   specialty: docs   risk: low   found: 1/8
- files: docs/src/changelogs/release_5_3.rst (exists)
- verdicts: decider-compat-risk and decider-triage: approve (A2-haiku)
- status: approved

## T-pymodaq_utils-M11 Shared input checks for ft/ift/ft2/ift2
- scope: pymodaq_utils   specialty: refactor   risk: medium   found: 1/8
- files: math_utils.py:374-478; pinning tests first in tests/math_utils_test.py
- verdicts: decider-compat-risk: approve with conditions; decider-test-change: veto in round 1 (tests insufficient), approve in round 2 with pinning tests first (A2-sonnet)
- status: proposed (touches tests)

## T-pymodaq_utils-M12 Drift test for the duplicated entry-point group lists
- scope: pymodaq (test only)   specialty: test-quality   risk: low   found: 1/8
- files: new test in packages/pymodaq/tests/ comparing pymodaq_utils/plugin_tools/checks.py:46-48 with pymodaq/utils/daq_utils.py:35-36
- verdicts: decider-compat-risk: approve in round 2 (placement); decider-test-change: approve in round 2 (B2)
- status: proposed (tests, outside the pymodaq_utils scope)

## Dropped
- Share get_entrypoints (A2-sonnet): compat-risk vetoed twice (return types differ, heavy imports); compat-risk itself says dropping is fine.
- Repo-wide style/typing (UP*, I001, W29x) and "trivial style fixes" (A3-sonnet): hard rule 5.
- radon refactors (check_extension_source F65, _literal_value F42, check_plugin_source E38): need a staged plan with characterisation tests.

## Blocked
- tests/config_test.py::test_nested_update_from_user fails on machines where the system and user config folders are the same
  (~/.pymodaq/config here; CI passes): the test writes its user file over its own system file. Candidate test-quality task.
