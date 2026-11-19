# Plan: pymodaq_utils — 2026-11-19
base commit: 7c76fcd78   mode: run   run id: 2026-11-19-utils-plan-B2
scan: .agents/scans/pymodaq_utils-4a0d17e7dcfc.md (sha256 56463aebdf196cb957a297d68870fb976e07ca7a0d2b812471867022016f2029)
experiment B run 2/2: advisors on haiku (default), every decisioner on sonnet.
isolation note: advisor-quality mentioned an earlier plan file (B1) in its output, so it read a file the experiment excludes. The coordinator did not read it. The triage prompt told the decisioner to ignore that mention.
arbiter ruling (binding): U1/U2 overlap on config.py and environment.py, U2/U3 on packages.py; no hunk conflicts, no merge. Independent PRs, merge order U1, U2, U3, then U4 and U6 in any order.

## T-pymodaq_utils-001 Remove unused imports (U1)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `config.py:3`, `config.py:11`, `config.py:13`, `environment.py:3`, `mysocket.py:8`, `serialize/mysocket.py:1`, `math_utils.py:7` (all under packages/pymodaq_utils/src/pymodaq_utils/)
- notes: keep Any/Union/TYPE_CHECKING in config.py and `datetime` in environment.py (used); in math_utils.py drop only one of the two `Union` imports.
- verdicts: decider-compat-risk: approve — names unused and not imported from these modules; decider-triage (2nd): approve — about 6 lines, one concern
- status: approved

## T-pymodaq_utils-002 Tighten exception handling (U2)
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `environment.py:153`, `packages.py:96`, `config.py:118`, `config.py:325-326`
- notes: bare `except:` becomes `except Exception:` (KeyboardInterrupt/SystemExit now propagate; say so in the PR body). At config.py:325 keep `as e` and add `from e`; remove the unused `e` only at :118.
- verdicts: decider-compat-risk: approve — no public name changed; decider-triage (2nd): approve — flags that "remove unused e at :325" conflicts with `from e`
- status: approved

## T-pymodaq_utils-003 Fix no-op comparison in extract_authors_from_description (U3)
- scope: pymodaq_utils   specialty: hygiene (adds a test)
- risk: medium
- files: `packages.py:207`, new test in packages/pymodaq_utils/tests
- notes: write a characterisation test first. When "Instruments" is absent `posi` stays -1 and `description[posa:-1]` drops the last character. The two decisioners disagree on the fix: compat says use `len(description)` as the fallback (not `posa+50`, which truncates the list), test-change reads the intent as `posa+50`. The human must pick the intended behaviour. No callers found in the repo; external use unverified.
- verdicts: decider-compat-risk: approve — only with a `len(description)`-style fallback and an explicit PR note; decider-test-change: approve — additive test, nothing weakened
- status: proposed (touches tests; fix intent undecided)

## T-pymodaq_utils-004 Deprecation warnings on moved plugin_tools shims (U4)
- scope: pymodaq_utils   specialty: hygiene (public API and tests)
- risk: medium
- files: `plugin_checks.py`, `plugin_rules.py`, `plugin_scaffold.py`, `docs/src/developer_folder/legacy_to_current.rst` (regenerate with docs/legacy_to_current.py, never by hand), new warning test
- notes: call `deprecation_msg` before the `sys.modules` swap and keep the `python -m` branch working. The test must drop the old name from `sys.modules` first, then use `pytest.warns`. The root pyproject ignores DeprecationWarning, so existing tests do not fail. Compat suggests repointing the `check_plugin` script in packages/pymodaq/pyproject.toml:76 to `pymodaq_utils.plugin_tools.checks:main`; that file is in scope `pymodaq`, so it is a separate follow-up. The PR may exceed 300 lines with the regenerated rst; split if so.
- verdicts: decider-compat-risk: approve — conditional, fixes the only hard-rule-1 gap; decider-test-change: approve — adds a warning and a test, no existing test edited
- status: proposed (public API and tests)

## T-pymodaq-005 Drift test for the duplicated entry-point group lists (U5)
- scope: pymodaq (not pymodaq_utils)   specialty: test-quality
- risk: low
- files: new file in `packages/pymodaq/tests/`, reads `pymodaq_utils/plugin_tools/checks.py:46-48` and `pymodaq/utils/daq_utils.py:35-36`
- notes: compare sets: the union of both `checks.py` tuples against `PLUGIN_ENTRYPOINT_GROUPS`. New file, no source change. A test in pymodaq_utils would break layering.
- verdicts: decider-compat-risk: approve (round 2) — only if in packages/pymodaq/tests; decider-test-change: veto in round 1 (placement), approve in round 2 — additive test, placement condition met
- status: proposed (tests)

## T-pymodaq_utils-006 Document import side effects of pymodaq_utils (U6)
- scope: pymodaq_utils   specialty: docs
- risk: low
- files: `__init__.py` (module docstring)
- notes: `import pymodaq_utils` sets up the logger (line 10), registers serializables via the serializer import (line 15), and creates `CONFIG` (line 23), which creates the config file if missing. The wrapping try/except (lines 2–30) only prints failures, so import errors are swallowed; say so. Leave the `__init__.py:15` re-exports alone.
- verdicts: decider-compat-risk: approve — claim verified in code; decider-triage (2nd): approve — docstring is the right place
- status: approved

## Rejected or deferred
- B006 mutable defaults (utils.py:444-511, math_utils.py:616, array_manipulation.py:151): public signature change, needs a compat audit.
- Vulture 60-79% names, `__init__.py:15` re-exports, duplicate public `get_entrypoints` (packages.py:159, utils.py:755): public API, keep (hard rule 1).
- config.py:23 `pymodaq_gui.Parameter` TYPE_CHECKING import: layering smell, not a runtime issue.
- Refactors (duplicate shims, math_utils clones, scaffold templates, radon hotspots, Config.__call__): low value or needs snapshot tests first.
- config.py:474-476 `_allow_direct_call` outside the lock: no evidence of a real race.
- Style-only counts: hard rule 5.
