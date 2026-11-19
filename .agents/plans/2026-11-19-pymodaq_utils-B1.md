# Plan: pymodaq_utils — 2026-11-19 (Experiment B, run 1: decisioners on sonnet)
base commit: 7c76fcd78   mode: run
run id: 2026-11-19-utils-plan-B1   scan: .agents/scans/pymodaq_utils-4a0d17e7dcfc.md (sha256 56463aebdf196cb957a297d68870fb976e07ca7a0d2b812471867022016f2029)

Merge order (decider-arbiter, binding): T2 before T4 (utils.py); T3 before T5 (mysocket.py). Four separate PRs, all from dev_agent.

## T-pymodaq_utils-001 Fix `posi == posa + 50` comparison in packages.py (touches tests)
- scope: pymodaq_utils   specialty: hygiene
- risk: medium
- files: `packages/pymodaq_utils/src/pymodaq_utils/packages.py:207`, new test in `packages/pymodaq_utils/tests/`
- notes: behaviour change (authors slice becomes capped at posa+50 when "Instruments" is missing; today it ends at -1). The test must pin exact output for: no "Instruments", no "Authors" (posa == -1), contributors marker without "Instruments". Only a human can confirm truncation is the wanted result.
- verdicts: decider-compat-risk: approve — real no-op bug, no public name touched, but visible behaviour change so keep proposed; decider-test-change: approve — adds a test, deletes/weakens none, conditional on exact-output assertions
- status: proposed

## T-pymodaq_utils-002 ThreadCommand: deprecated `attributes=` value is overwritten with None (touches tests)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `packages/pymodaq_utils/src/pymodaq_utils/utils.py:365-369`, new test in `packages/pymodaq_utils/tests/utils_test.py`
- notes: make line 369 an `else:` branch. Tests: `attributes=[1,2]` sets `.attribute` and `.attributes`; explicit `attribute=` wins when both given. Do not edit existing tests. Merge before T-004.
- verdicts: decider-compat-risk: approve — no repo caller passes `attributes=`; restores documented deprecation behaviour; decider-test-change: approve — no existing test encodes the bug, none edited
- status: proposed

## T-pymodaq_utils-003 check_received_length spins forever when peer closes (touches tests)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `packages/pymodaq_utils/src/pymodaq_utils/mysocket.py:86-92`, new fake-socket test
- notes: raise `ConnectionError` (message with expected/received byte counts) when `recv` returns `b''`. `serialize/mysocket.py` has no such loop (SocketString only slices), so one fix covers both; `serializer_legacy.py` callers use SocketString and are unaffected. Test: partial data then `b''` raises; complete read unchanged. External TCP code outside the repo unverified. Round 1 split (test-change vetoed on missing plan entry / coverage diff, which do not apply to an added test); round 2 both approve. Merge before T-005.
- verdicts: decider-compat-risk: approve — ConnectionError subclasses OSError, only peer-closed path changes; decider-test-change: approve (round 2) — adds a test, no existing test touched
- status: proposed

## T-pymodaq_utils-004 Replace mutable default `paths=[]` in recursive_find_* (no tests)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `packages/pymodaq_utils/src/pymodaq_utils/utils.py:444`, `:458`, `:475` (+ stale docstring notes at ~447, 463, 482)
- notes: `paths=None` plus `if paths is None: paths = []`. Narrowed by compat review: leave out `utils.py:511` (`count_lines` has no mutable `paths`), `array_manipulation.py:151` and `math_utils.py:616` (defaults only read, never mutated). Merge after T-002.
- verdicts: decider-compat-risk: approve — only in-repo callers are two tests passing no `paths`; decider-triage (2nd): approve — ~15 lines, near-zero risk
- status: approved

## T-pymodaq_utils-005 Hygiene: bare excepts, unused `e`, unused imports (no tests)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `environment.py:153`, `packages.py:96` (`except:` -> `except Exception:`); `config.py:118`, `:325` (unused `e`), `:326` (`raise ... from`); unused imports `config.py:3` (abstractproperty), `:11` (datetime), `:13` (List), `environment.py:3` (glob), `mysocket.py:8` (Union), `math_utils.py:7` (duplicate `Union` only)
- notes: out of scope: `abstract.py:12` `abstractmethod` is imported from `pymodaq` (`module_saving.py:16`), keep it. In `mysocket.py` touch only line 8. Remaining F401 removals and `config.py:23` (pymodaq_gui import, layering smell) are not in this task. Merge after T-003.
- verdicts: decider-compat-risk: approve — names grepped in packages/ and docs/, none re-exported except abstractmethod (excluded); decider-triage (2nd): approve — one concern, well under 300 lines
- status: approved

## Not tasked
- Rejected or deferred by triage: `config.py:23` Parameter import (layering; needs separate compat check), `serializer_legacy.py:13` TYPE_CHECKING imports, config atexit + `__del__` double save, scaffold `'Update_Status'` strings (deprecation unverified), cosmetic style codes, radon/jscpd refactors, `to_dict` deepcopy and quadratic `bytes +=` (unmeasured), `platforms.py:192` PYTHON_VERSIONS (tied to PR #1509).
- Experiment note: decider-compat-risk (T1) and decider-test-change (T3 round 1) read `.agents/handoff/` / `.agents/plans/` despite the isolation instruction; their T3 round-1 veto cited another plan's task numbering.
