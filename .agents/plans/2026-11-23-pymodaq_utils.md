# Plan: pymodaq_utils — 2026-11-23
base commit: 3f73bc40b17cdef03b30f81f5b989c8b874fdff3   mode: run
scan: .agents/scans/pymodaq_utils-038f36a763db.md (sha256 a2547e7fc82b19b2fd5b7770e5283698cb21240d9edd73c2a9d5340e067ed952)
Constraints: grill config-isolation (answered). GRILL open: config-reconcile (schema reconcile finding gets no task until answered).
Open findings at planning time (verbatim keys): pymodaq_utils/config.py:load|schema drift and shared folders; utils-config-nested-update-fail; pymodaq_utils/logger.py:unused sys import; packages/pymodaq_utils/src/pymodaq_utils/__init__.py:ConfigError handler|untested; packages/pymodaq_utils/src/pymodaq_utils/logger.py:set_logger|double config lookup; packages/pymodaq_utils/tests/config_test.py:test_load_system_config|shared real folders; config.py:get_set_local_dir|PYMODAQ_CONFIG_DIR + save guard; config.py:BaseConfig.load|schema reconcile; agents:tools.env|throwaway HOME.
Order: T-012 -> T-013 (arbiter: T-012 only adds tests to config_test.py; T-013 after T-012 merged owns edits to existing tests + conftest). T-011 (blocked, packages.py) not duplicated.

## T-pymodaq_utils-012 PYMODAQ_CONFIG_DIR override and Config.save pytest guard
- scope: pymodaq_utils/config.py   specialty: refactor
- risk: medium (public API addition, fork-only first)
- files: `packages/pymodaq_utils/src/pymodaq_utils/config.py:109-147` (get_set_local_dir, cache key must include the env var, cache_clear kept), `config.py:443` (save guard: log a warning and return, never raise), `packages/pymodaq_utils/tests/config_test.py` (new test functions only)
- finding: config.py:get_set_local_dir|PYMODAQ_CONFIG_DIR + save guard
- conditions: unset var leaves paths unchanged; <dir>/system and <dir>/user; coverage before/after on config.py and config_test.py, test count not lower, both Qt backends (decider-test-change mandatory); a minimal autouse conftest fixture only if the guard breaks existing tests. No reconcile/schema work.
- verdicts: decider-compat-risk: approve — signature unchanged, conditions above; decider-test-change: approve (round 2) — veto lifted given the mandatory coverage/count conditions
- notes: owner guidance for the rework (2026-11-24), on top of the five review findings: (1) prefer the narrow guard rule: under pytest, save() writes only if self.config_path is inside PYMODAQ_CONFIG_DIR (Path.is_relative_to), otherwise warn and return; avoid a bare `'pytest' in sys.modules` test that would also trip plugin developers who import pytest outside a test run; the atexit path needs its own test. (2) Dropping cache_info/__wrapped__ from get_set_local_dir is accepted: say so in the PR body.
- status: done — PR #22 merged by the human

## T-pymodaq_utils-013 Conftest isolation of the user config, fix test_load_system_config
- scope: pymodaq_utils/tests   specialty: test-quality
- risk: medium (tests)
- files: `packages/pymodaq_utils/tests/conftest.py` (new or extended), `packages/pymodaq_utils/tests/config_test.py:124-138` (test_load_system_config: isolate dir, copy TOML_DICT instead of mutating; assertions identical), `config_test.py:267-276` (re-check test_nested_update_from_user; split into its own task if still failing, never skip)
- finding: packages/pymodaq_utils/tests/config_test.py:test_load_system_config|shared real folders; utils-config-nested-update-fail
- depends on: T-pymodaq_utils-012 merged
- conditions: same decider-test-change mandatory list as T-012; hard rule 2
- verdicts: decider-compat-risk: approve — tests only; decider-test-change: approve (round 2) with mandatory conditions
- status: approved — owner, 2026-11-24 (runs after T-012 is merged)

## T-pymodaq_utils-014 Test the ConfigError handler in the package import
- scope: pymodaq_utils/tests   specialty: test-quality
- risk: low
- files: `packages/pymodaq_utils/src/pymodaq_utils/__init__.py:39,47`
- finding: packages/pymodaq_utils/src/pymodaq_utils/__init__.py:ConfigError handler|untested
- verdicts: decider-compat-risk: veto — premise false: __init__.py has no `except ConfigError`, only `except Exception` at 39 and 47; decider-test-change: veto — same
- status: blocked — premise false on dev_agent (no ConfigError handler in __init__.py; likely on an unmerged T-007 branch). Rewrite the finding against the `except Exception` fallbacks (reload with a patched GlobalConfig that raises) or drop.

## T-pymodaq_utils-015 Trivial lint cleanups, numpydoc underline, double config lookup
- scope: pymodaq_utils   specialty: hygiene
- risk: low
- files: `enums.py:85` (B007), `enums.py:55` (SIM102: only merge the nested if, keep the super().__eq__ fallback), `utils.py:731` (B007), `utils.py:475,649,711` (SIM102), `environment.py:192-193` (E741), `environment.py:96,100` (F541), `environment.py:138-139` (numpydoc underline 7 dashes), `array_manipulation.py:24` (SIM103, keep bool), `array_manipulation.py:143,145` (E703), `plugin_tools/checks.py:247` (SIM102), `plugin_tools/platforms.py:131` (SIM105), `__init__.py:35,37` (F541), `logger.py:45` (reuse log_level)
- finding: packages/pymodaq_utils/src/pymodaq_utils/logger.py:set_logger|double config lookup
- notes: packages.py:156 F541 excluded (T-011 owns packages.py); touch only cited lines (hard rule 5); run pymodaq_utils tests under both Qt backends; may split if over 300 lines
- verdicts: decider-compat-risk: approve — citations verified, enums condition above; decider-triage (fresh): approve — behaviour-preserving, backends condition
- status: done — PR #21 merged (auto: low risk, approved by decider-compat-risk, decider-triage, reviewer approve, 59 lines, no tests/UI/API)

## T-pymodaq_utils-016 Throwaway HOME for the agents' test checks
- scope: .agents tooling   specialty: tool
- risk: low (no product source; branch agent-tool/throwaway-home)
- files: `.agents/scripts/*` (check runner), `.agents/profile.toml` `[tools].env`/`[checks]`
- finding: agents:tools.env|throwaway HOME
- conditions: set HOME and USERPROFILE only for test-check commands; PATH expanded with the real HOME before the swap; ci.py/gh/git keep the real HOME; report says the system folder (/etc/.pymodaq) is not isolated and pymodaq/gui suites + Windows are unverified
- verdicts: decider-compat-risk: approve — grill answer 5; decider-triage (fresh): approve — verified for 335 + 655 tests
- status: done — merged into dev_agent by hand (a57ae95b2) as the bounded, isolated test checks: throwaway HOME, time limit with stack dump, flaky rerun, baseline rerun

## Not tasked
- GRILL config-reconcile (finding config.py:BaseConfig.load|schema reconcile and the schema part of config.py:load|schema drift): `.agents/grill/config-reconcile.md`.
- Dropped: stale `import sys` (sys used at logger.py:48); B006 mutable defaults, F401 re-exports, vulture, serializer_legacy TYPE_CHECKING import, B024, radon hotspots, jscpd, style churn, GlobalConfig RLock (unverified deadlock), compat notes.
