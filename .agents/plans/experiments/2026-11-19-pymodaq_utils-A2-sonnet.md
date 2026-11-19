# Plan: pymodaq_utils — 2026-11-19 (Experiment A2-sonnet)
base commit: b12c5a5be   mode: run
scan: .agents/scans/pymodaq_utils-4a0d17e7dcfc.md (sha256 f521dfc42a71ec6f5d9a87430569e98842404aab0f5923f3d0090b5a8cde717e)
run id: 2026-11-19-utils-plan-A2-sonnet; advisors on sonnet. Arbiter: H1 and B1 both touch packages.py (lines 96 / 207), separate PRs, H1 merges first, B1 rebased on it.

## T-pymodaq_utils-001 Narrow bare excepts, drop unused `e`
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `environment.py:153`, `packages.py:96`, `config.py:118`
- notes: `except Exception`. At config.py:325-326 `e` is used by `raise ... from e`; keep it there, only drop the unused `e` at config.py:118 (compat-risk). Optional `raise ... from` at config.py:326 already uses it.
- verdicts: decider-compat-risk: approve — only lets KeyboardInterrupt/SystemExit through; decider-triage (fresh): approve — real bare excepts; decider-test-change: approve — no test reaches them
- status: approved

## T-pymodaq_utils-002 Remove unused non-re-export imports
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `config.py` (abstractproperty, datetime, List, TYPE_CHECKING Parameter import), `environment.py:3`, `mysocket.py:8`, `serialize/mysocket.py:1`, `math_utils.py:7`
- verdicts: decider-compat-risk: veto as written — `abstract.py:12` `abstractmethod` is imported by pymodaq h5modules/module_saving.py:16; decider-triage: veto as written — same finding, would approve without abstract.py
- status: blocked — both decisioners vetoed the task as written (abstract.py:12). Both would approve it WITHOUT `abstract.py:12`; human to confirm the reduced scope, then it can be re-queued.

## T-pymodaq_utils-003 Fix no-op comparison in extract_authors_from_description
- scope: pymodaq_utils   specialty: hygiene (bug fix + new tests)
- risk: medium
- files: `packages.py:207` + new test in packages tests
- notes: set `posi = len(description)` when "Instruments" is missing (NOT `posa + 50`, which would cut at 50 chars). Output changes (bug fix: last char no longer dropped, Contributors marker respected); say so in PR. Exact-list tests: Instruments present; missing with Contributors; missing without Contributors; one newline before Instruments.
- verdicts: decider-compat-risk: round 1 veto of `posa+50`, round 2 approve reworded; decider-test-change: round 1 approve, round 2 approve reworded (no existing test touches it)
- status: proposed

## T-pymodaq_utils-004 recursive_find_* shared mutable default
- scope: pymodaq_utils   specialty: hygiene (bug fix + new test)
- risk: medium
- files: `utils.py:444,458,475` + new test in utils_test.py
- notes: `paths=None` with `if paths is None: paths = []`; update docstring notes (utils.py:447,463,482). Test: two calls on a tmp_path give equal results; explicit list still filled.
- verdicts: decider-compat-risk: approve — explicit-list callers unchanged; decider-test-change: approve — existing test only checks non-empty
- status: proposed

## T-pymodaq_utils-005 Share get_entrypoints between packages.py and utils.py
- scope: pymodaq_utils   specialty: refactor
- risk: low
- files: `packages.py:159-179`, `utils.py:755-777`
- verdicts: decider-compat-risk: veto (round 1 and 2) — return types differ (EntryPoints vs list) and utils would drag requests/lxml imports; only a narrow private importlib.metadata-only helper (~7 lines saved) is acceptable; decider-triage: approve — original wording, did not review narrow form
- status: blocked — split remains; human decides whether the ~7-line gain is worth the narrow helper (compat-risk itself says dropping is fine)

## T-pymodaq_utils-006 API doc pages for config, logger, enums
- scope: docs (docs/src)   specialty: docs
- risk: low
- files: new .rst under the existing API autodoc folder (find it first; docs/src/api not confirmed); never edit legacy_to_current.rst
- notes: record `sphinx-build -W` baseline first.
- verdicts: decider-compat-risk: approve — new pages only; decider-triage: approve — no existing automodule pages
- status: approved

## T-pymodaq_utils-007 API doc pages for plugin_tools
- scope: docs   specialty: docs
- risk: low
- files: new .rst for plugin_tools checks, scaffold, contract, platforms
- verdicts: decider-compat-risk: approve; decider-triage: approve — instrument_plugins.rst names them without API pages
- status: approved

## T-pymodaq_utils-008 Shared input checks for ft/ift/ft2/ift2
- scope: pymodaq_utils   specialty: refactor (tests first)
- risk: medium
- files: `math_utils.py:374-478` + new tests in math_utils_test.py
- notes: same PR first adds pinning tests (existing tests untouched, exact exception types and messages): ft2/ift2 known-array output; ft("list",1.5) TypeError vs ft2("list",1.5) AssertionError; ft(x,-2) AssertionError; ft2 d==ndim -> numpy AxisError; negative d. Two helpers (check order differs between ft/ift and ft2/ift2). Do NOT fix ft2 ignoring `dim` in fft2. Coverage must not drop.
- verdicts: decider-compat-risk: approve (round 1 and 2, with conditions); decider-test-change: round 1 veto (tests insufficient), round 2 approve with pinning tests first
- status: proposed

## Dropped by triage
Other B006 defaults (never mutated), safe_pickle `pid` (persistent_load override), serializer_legacy imports (string hints), cosmetic F541/E741/semicolons (hard rule 5), B024, mysocket shim duplicate, re-exports, plugin_tools complexity, vulture 60-79%, RLock/to_dict/atexit ideas (unproven).
