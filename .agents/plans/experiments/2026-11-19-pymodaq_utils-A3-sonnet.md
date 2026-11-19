# Plan: pymodaq_utils — 2026-11-19 (Experiment A3-sonnet)
base commit: 8f7ab4340caef0a0aca4e587bf7e704fdc082551   mode: run
run id: 2026-11-19-utils-plan-A3-sonnet   scan: .agents/scans/pymodaq_utils-4a0d17e7dcfc.md
advisors on sonnet; arbiter ruling: execution order T-003 -> T-004 -> T-001; T-002 independent. Re-locate lines by content after rebasing.

## T-pymodaq_utils-001 Fix `posi == posa + 50` comparison in extract_authors_from_description
- scope: pymodaq_utils   specialty: hygiene
- risk: medium (behaviour change when no "Instruments" heading: slice now ends at posa+50, may cut long author lists)
- files: `packages/pymodaq_utils/src/pymodaq_utils/packages.py:207`, new test in `packages/pymodaq_utils/tests/`
- verdicts: decider-compat-risk: approve — real bug, signature unchanged, no other caller in repo; decider-test-change: approve — only adds a test, no existing test touched
- conditions: regression test with no "Instruments" and >=2 authors, assert exact output, cover "Contributors" before posa+50; state whether the 50-char cap is intended; attach coverage diff
- status: proposed (touches tests)

## T-pymodaq_utils-002 Replace shared `paths=[]` default with None
- scope: pymodaq_utils   specialty: refactor
- risk: medium
- files: `packages/pymodaq_utils/src/pymodaq_utils/utils.py:444`, `:458`, `:475` (+ docstring warnings), new test in `packages/pymodaq_utils/tests/utils_test.py`
- verdicts: decider-compat-risk: approve — explicit-list callers unchanged, only cross-call accumulation goes away; decider-test-change: approve — existing tests (utils_test.py:209-220) unaffected, test added
- conditions: new test uses tmp_path, calls each function twice, must fail on current code; leave `filters=[...]` defaults alone; no reformatting
- status: proposed (tests, public signature default)

## T-pymodaq_utils-003 Exception hygiene
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `config.py:118`, `config.py:325-326`, `environment.py:153`, `packages.py:96` (under packages/pymodaq_utils/src/pymodaq_utils/)
- verdicts: decider-compat-risk: approve — no type/message/signature change; decider-triage (fresh): approve — one concern, ~6 lines
- status: approved

## T-pymodaq_utils-004 Remove unused imports and trivial style fixes (merged former T4 + T5 by arbiter)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `config.py:3,11,13`, `environment.py:3,97,101`, `math_utils.py:2` (keep line 7 Union), `mysocket.py:8`, `serialize/mysocket.py:1`, `__init__.py:14,16`, `packages.py:156`, `array_manipulation.py:143,145`
- verdicts: decider-compat-risk: approve — no external import of removed names found in packages/; decider-triage (fresh): approve — all verified unused; T5 part: both approve
- conditions: edit only listed lines (hard rule 5); do not "fix" pre-existing ruff format failures; run layering test
- status: approved

## Dropped / not tasked
- Re-exports (`__init__.py:15`, `serialize/factory.py:3`, `serialize/serializer.py:3`, `serializer_legacy.py:13`), vulture 60-79% public API, ObjectFactory B024, safe_pickle `pid`: hard rule 1.
- `abstract.py:12 abstractmethod`: used by pymodaq module_saving.py:16. `config.py:23`: already under TYPE_CHECKING.
- B006 at array_manipulation.py:151, math_utils.py:616, `filters` lists: only read, signature change for no gain.
- Deferred: radon complexity in plugin_tools/rules.py and utils.py, jscpd clones, mysocket duplicate shim, plugin_tools automodule docs page.
- Performance advisor: nothing for this scope.

Blocked: none.
