# Plan: pymodaq_utils — 2026-11-19 (Experiment A3-haiku)
base commit: 8f7ab4340   mode: run
scan: .agents/scans/pymodaq_utils-4a0d17e7dcfc.md (sha256 24005128f722d7873ae0675b2860d1d60d92e40111c68e2ba22aab861110c438)
arbiter ruling: merge triage tasks "dead imports" + "exception handling" into T-001 (same files); keep the `==` bug fix separate (T-002, revertable); T-003 independent. Order: T-001 lands first, T-002 rebases onto it.

## T-pymodaq_utils-001 Hygiene: dead imports + exception handling
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `config.py:3,11,13,22-23` (abstractproperty, datetime, List, TYPE_CHECKING-only pymodaq_gui Parameter + the now-empty TYPE_CHECKING block and unused TYPE_CHECKING name), `environment.py:3` (glob), `mysocket.py:8` (Union), `serialize/mysocket.py:1` (Any, Union, TYPE_CHECKING), `math_utils.py:2|7` (remove ONE duplicate Union; the module is star-imported by pymodaq), `packages.py:96` and `environment.py:153` (bare except -> except Exception), `config.py:118` (unused `e`), `config.py:325-326` (`raise ... from e`)
- verdicts: decider-compat-risk: approve — no public name removed, grep found no importer of the dropped names, low risk (T-002 and T-003 both reviewed); decider-triage (fresh, second opinion): approve — each import unused, exception types unchanged; arbiter: merged
- conditions: grep monorepo for `from pymodaq_utils.<module> import <name>` before deleting each import; touch only the listed lines (hard rule 5); commit message notes KeyboardInterrupt/SystemExit now propagate at the two former bare excepts; tests under PyQt6 and PySide6, layering test, flake8 blocking set. If compat-risk judges the except change more than hygiene, split it out.
- status: approved

## T-pymodaq_utils-002 Fix `posi == posa + 50` in extract_authors_from_description
- scope: pymodaq_utils   specialty: hygiene (touches tests: adds a new test)
- risk: medium
- files: `packages/pymodaq_utils/src/pymodaq_utils/packages.py:207`, new test under `packages/pymodaq_utils/tests/`
- verdicts: decider-compat-risk: approve (conditions) — real bug, function has no callers in repo, but output changes when the description has no "Instruments" (cap becomes posa+50, may cut long author lists); decider-test-change: approve — test is purely additive, no existing test touched
- conditions: write the test against current code first (no "Instruments", 2+ authors, Contributors within and beyond 50 chars of "Authors"); PR states whether the 50-char cap is intended (otherwise `len(description)` is a separate change); attach coverage diff; external callers unverified
- status: proposed

## T-pymodaq_utils-003 Mutable `paths=[]` defaults -> `None`
- scope: pymodaq_utils   specialty: refactor (public signature, touches tests)
- risk: low (compat-risk) — API-adjacent, kept proposed
- files: `packages/pymodaq_utils/src/pymodaq_utils/utils.py:444,458,475`, `packages/pymodaq_utils/tests/utils_test.py` (new test for all three functions, using tmp_path)
- verdicts: decider-compat-risk: approve — recursive calls pass `paths` along, explicit lists behave the same, no repo caller depends on accumulation; decider-test-change: approve — existing tests only assert non-empty, new test is additive
- conditions: update docstrings at utils.py:447, 462-463, 482-483 (they describe the shared list); leave `filters=[...]` defaults alone; external plugins unverified
- status: proposed

## Dropped by triage (no task)
- instrument_plugins.rst:208 version mismatch (rst already correct); scaffold.py:44 and config.py:348-349 layering (template string / guarded optional import); abstract.py:12 re-export (used by pymodaq); B006 at array_manipulation.py:151 and math_utils.py:616 (read-only); rules.py complexity (needs output-locking tests first, deferred); jscpd clones, get_entrypoints duplicate (needs caller audit + shim); ruff style batch (hard rule 5); vulture 60-79% and `__init__` registration imports (false positives); legacy_to_current.rst (generated); platforms.py:192 PYTHON_VERSIONS lacks 3.14 (owner decision, may overlap PR #1509).
