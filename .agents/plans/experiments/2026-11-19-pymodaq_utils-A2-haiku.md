# Plan: pymodaq_utils — 2026-11-19
base commit: b12c5a5be   mode: run   run-id: 2026-11-19-utils-plan-A2-haiku
scan: .agents/scans/pymodaq_utils-4a0d17e7dcfc.md (sha256 f521dfc42a71ec6f5d9a87430569e98842404aab0f5923f3d0090b5a8cde717e)
order (arbiter): T-001 -> T-002 -> T-003 -> T-004 -> T-007; T-006 parallel; T-005 parallel, own branch.
Same-day branch rule: one branch per specialty per date, so T-002, T-003, T-004 (all hygiene) need distinct dates/branches.
Decisioner calls were batched per kind (one compat-risk, one test-change, one fresh triage call for all findings).

## T-pymodaq_utils-001 ThreadCommand drops deprecated `attributes=`
- scope: pymodaq_utils/utils   specialty: refactor
- risk: low
- files: `packages/pymodaq_utils/src/pymodaq_utils/utils.py:365-369`; add regression test in `packages/pymodaq_utils/tests/utils_test.py`
- note: line 369 overwrites `self.attribute` with None; add `else`. Test must expect the deprecation warning. Adds a test only.
- verdicts: decider-compat-risk: approve — restores documented behaviour, no in-repo caller passes attributes=; decider-test-change: approve — only adds coverage
- status: approved

## T-pymodaq_utils-002 Mutable default arguments in recursive_find_*
- scope: pymodaq_utils/utils   specialty: hygiene
- risk: low
- files: `utils.py:444`, `utils.py:458-459`, `utils.py:475-476`, `utils.py:511`; docstrings 447/463/482; add test
- note: `None` sentinel, keep names and behaviour; keep passing `paths` in recursive calls (454, 467, 488); do not change filters recursion at 522. Public signature default changes, so left proposed.
- verdicts: decider-compat-risk: approve — callers passing paths see no change; decider-test-change: approve — utils_test.py:213/220 do not rely on accumulation
- status: proposed

## T-pymodaq_utils-003 Unused imports and names (merged F3+F4+F6, per arbiter)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `config.py:3,11,13,22-23` (abstractproperty, datetime, List, Parameter, empty TYPE_CHECKING block), `config.py:118`, `config.py:325-326` (`raise ... from e`), `enums.py:86`, `utils.py:724`, `math_utils.py:7` (remove duplicate Union ONLY), `environment.py:3`, `mysocket.py:8`, `serialize/mysocket.py:1`, `__init__.py:15` (`# noqa: F401` with reason), `packages/pymodaq/tests/layering_test.py:20` (stale allowlist entry; keep lines 21-22)
- note: do NOT touch `abstract.py:12` (abstractmethod is re-exported, used by pymodaq module_saving.py:16). Do not drop List/Tuple from math_utils (star-imported by pymodaq). If layering_test edit is refused, drop config.py:22-23 and the allowlist line.
- verdicts: decider-compat-risk: approve (revised scope; original F6 vetoed for abstract.py:12) — nothing imports the removed names from config; decider-test-change: approve — allowlist cleanup tightens, not weakens; decider-triage(fresh): approve revised scope
- status: proposed   (touches a test file)

## T-pymodaq_utils-004 Bare except -> except Exception
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `environment.py:153`, `packages.py:96`
- note: only change is KeyboardInterrupt/SystemExit no longer swallowed.
- verdicts: decider-compat-risk: approve — Exception covers the handled errors; decider-triage(fresh): approve — mechanical
- status: approved

## T-pymodaq_utils-005 Shims plugin_checks/rules/scaffold lack deprecation_msg
- scope: pymodaq_utils (+ packages/pymodaq/pyproject.toml, outside scope)   specialty: refactor
- risk: medium
- files: `plugin_checks.py`, `plugin_rules.py`, `plugin_scaffold.py`, `packages/pymodaq/pyproject.toml:76`, `docs/src/developer_folder/legacy_to_current.rst` (regenerate with docs/legacy_to_current.py, never by hand)
- note: call deprecation_msg BEFORE the sys.modules swap so plugin_contract_test.py:36 still passes; repoint check_plugin script to plugin_tools.checks:main in the same PR; keep PMQ rule codes. The "plugin_testing.py:20 symbol" sub-item is unverified (line is correct); the stale text is the docstring at plugin_tools/checks.py:5. Whether external plugin CI treats warnings as errors is unverified.
- verdicts: decider-compat-risk: approve — gap vs hard rule 1 confirmed; decider-triage(fresh): approve with conditions above
- status: proposed   (public API)

## T-pymodaq_utils-006 Release note for the plugin_tools move
- scope: docs   specialty: docs
- risk: low
- files: `docs/src/changelogs/release_5_3.rst`
- note: put under a patch-release subsection (shims deprecated in 5.3.5), not the 5.3.0 text.
- verdicts: decider-compat-risk: approve — docs only; decider-triage(fresh): approve
- status: approved

## T-pymodaq_utils-007 No-op comparison in author parser
- scope: pymodaq_utils/packages   specialty: refactor
- risk: medium
- files: `packages.py:207`
- note: `posi == posa + 50` is a no-op, but naively turning it into an assignment would truncate the authors block 50 chars after "Authors" (regression). Probable correct fix is `posi = len(description)`. No test exists; pin behaviour with a test first, owner decides intent.
- verdicts: decider-compat-risk: not approved — changes parsed output, owner decision; decider-test-change: veto — untested, likely regression
- status: blocked   (needs human)

## Dropped (not tasks)
Mutable defaults at math_utils.py:616 and array_manipulation.py:151 (not mutated); duplicate get_entrypoints (needs shim); math_utils clones; radon hotspots; deepcopy under read lock (unprofiled); factory.py B024; style counts; serialize re-exports, serializer_legacy TYPE_CHECKING imports, safe_pickle pid, vulture 60-79%.
