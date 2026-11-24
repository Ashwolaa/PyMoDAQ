# Plan: pymodaq_utils — 2026-11-19 (r2, new scan)
base commit: fff891935   mode: run   scan: .agents/scans/pymodaq_utils-45ab1aceab89.md (sha256 b063d052ec474d0dead456baec8f58bb3c81068f0e52794d89567eac06e03410)
Complements 2026-11-19-pymodaq_utils.md (T-001..T-005). Re-check every file:line against HEAD before executing (plans expire after 14 days).
Correction (owner's session, 2026-11-19, after this plan was written): T-002..T-005 of the earlier plan were already
done as M04, M07, M01, M05 of the merged plan (PRs #4, #9, #5, #8); that plan showed them as open by mistake. So in the
ruling below T-002 and T-004 are done (drop them from the order), and the T-003 parts are already merged in #9: T-006
still rewrites the Config.__call__ docstring to match the code after its deletion; T-009 only checks that the
`_literal_value` docstring merged in #9 is still right. Effective order: T-006, T-011, T-007, T-009, T-008 (T-010 independent).
Arbiter ruling (binding), merge order, each a separate PR rebased on dev_agent after the previous merge:
T-002 (earlier plan), T-006, T-004 (earlier plan), T-011, T-007, T-009, T-008.
- The Config.__call__ docstring part of T-003 is merged into T-006 (T-003's text "plural falls back to singular on KeyError" is false after T-006; re-verify against the code).
- The utils.py `_literal_value` docstring part of T-003 is merged into T-009 (docs-only, runs after the code tasks).
- T-008 runs after T-002 and T-006; `test_nested_update_from_user` must be fixed by it (fails locally on dev_agent).

## Open findings (step 3b, verbatim)
- open pymodaq_utils seen 1x Config.__call__: the backends->backend and debug_levels->debug_level fallbacks catch KeyError, but the base __call__ raises ConfigError (config.py:326), so they never run (config.py:553,568; verified) | key: pymodaq_utils/config.py:Config.__call__|plural fallback never runs | evidence: .agents/reports/pymodaq_utils/2026-11-19-pr-review-T-pymodaq_utils-M07.md
- open pymodaq_utils seen 1x set_logger calls sys.exit(-1) when debug_level is not a list (logger.py:47); SystemExit passes the except Exception of pymodaq_utils/__init__.py, so importing the package can exit the interpreter (verified; reachability through Config.__call__ unverified) | key: pymodaq_utils/logger.py:set_logger|sys.exit on import | evidence: .agents/reports/pymodaq_utils/2026-11-19-pr-review-T-pymodaq_utils-M09-r2.md
- open pymodaq_utils seen 1x No docstring on GlobalConfig, ConfigError, get_config_file, StrEnum, get_base_logger, Severity: autodoc drops them, so M08 left them off the API pages | key: pymodaq_utils:docstrings|six public names undocumented | evidence: .agents/reports/pymodaq_utils/2026-11-19-pr-review-T-pymodaq_utils-M08.md
- open pymodaq_utils seen 1x config_test::test_nested_update_from_user fails locally on both Qt backends (passes in CI): the system and user config folders coincide (~/.pymodaq/config), so the test is not isolated from the user's config | key: pymodaq_utils/tests/config_test.py:test_nested_update_from_user|local failure | evidence: .agents/handoff/T-pymodaq_utils-M08.md

## T-pymodaq_utils-006 Delete the dead plural fallbacks in Config.__call__ (absorbs the Config.__call__ part of T-003)
- scope: pymodaq_utils   specialty: refactor (bugfix)   risk: low (delete option only)
- files: `packages/pymodaq_utils/src/pymodaq_utils/config.py:568-602` (the three `except KeyError` branches: backends, debug_levels, dynamics), docstring `config.py:552-554`; new test in `tests/config_test.py`
- finding: pymodaq_utils/config.py:Config.__call__|plural fallback never runs
- constraints: delete option, all three branches (compat-risk found `dynamics` 598-602 too); do NOT catch ConfigError (would change returned values: medium risk). Characterisation test pins current behaviour: missing plural key raises ConfigError, present plural key returns its value (fixture tests/data/config_template.toml). The line cited as config.py:326 is `__contains__`; the raise is at :322. Merge T-003's Config.__call__ docstring text, rewritten to match the code after the deletion.
- verdicts: decider-compat-risk: approve — dead branches, no caller-visible change with the delete option; decider-test-change: approve — test only added, existing tests untouched
- status: done — PR #18 open, awaiting the human: touches tests: packages/pymodaq_utils/tests/config_test.py

## T-pymodaq_utils-007 set_logger must not kill the importing process
- scope: pymodaq_utils   specialty: refactor (bugfix)   risk: medium
- files: `logger.py:43-48` (set_logger), `__init__.py:39-47` (message shown), new test in `tests/logger_test.py`
- finding: pymodaq_utils/logger.py:set_logger|sys.exit on import
- constraints: step 1 show reachability (fires only if debug_level is not a list AND a `debug_levels` key exists whose value is not a list, via GlobalConfig.__call__ config.py:588-597); if unreachable, end the task with a report and no code change. Otherwise raise a specific `Exception` subclass (ConfigError/ValueError, not SystemExit) with the same message; the message must stay visible when raised inside `__init__.py` (line 40's message "Couldn't create the local folder..." would mislead). Test builds a real debug_level/debug_levels config. Same signature and return type. Attach before/after coverage diff of logger.py and the test-agent justification. Do not reformat logger.py (rule 5).
- verdicts: decider-compat-risk: approve — status proposed, medium-low risk; decider-test-change: approve (round 2, after provisional veto for missing evidence) — conditional on coverage diff
- status: blocked — review: set_logger now raises ConfigError, with the same message, instead of calling sys.exit on a scalar debug_level, and the pymodaq_utils import prints that message;

## T-pymodaq_utils-008 Isolate test_nested_update_from_user
- scope: pymodaq_utils   specialty: test-quality   risk: low
- files: `tests/config_test.py:236-261` only
- finding: pymodaq_utils/tests/config_test.py:test_nested_update_from_user|local failure
- constraints: `monkeypatch.setattr(pymodaq_utils.config, 'get_set_local_dir', lambda user=False: <distinct pre-created tmp_path dir>)` (get_set_local_dir is functools.cache'd, config.py:125, so patching CONFIG_BASE_PATH/Path.home alone leaks). Keep the assertions at :258-259 unchanged. Attach the failing traceback and a before/after coverage diff of config.py (must not drop). Out of scope (file as finding): `test_load_system_config` (config_test.py:113-136) shares the same folders and mutates global TOML_DICT.
- verdicts: decider-compat-risk: approve — tests only; decider-test-change: approve (round 2, after procedural veto) — conditional on traceback + coverage diff + unchanged assertions
- status: done — PR #19 open, awaiting the human: a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; touches tests: packages/pymodaq_utils/tests/config_test.py

## T-pymodaq_utils-009 Docstrings for six public names (absorbs the _literal_value part of T-003)
- scope: pymodaq_utils   specialty: docs   risk: low
- files: `config.py:148` get_config_file, `config.py:268` ConfigError (replace `pass` by the docstring), `config.py:441` GlobalConfig, `enums.py:12` StrEnum, `logger.py:85` get_base_logger, `plugin_tools/rules.py:116` Severity; plus T-003's `utils.py:68-75` _literal_value docstring (text constraints in the earlier plan)
- finding: pymodaq_utils:docstrings|six public names undocumented
- constraints: docstrings only, written from what the code does (e.g. get_base_logger loops forever if no ancestor is named `pymodaq`: verify before stating); add only docstring lines (rule 5); run last of the code tasks. Once documented, the API pages that M08 trimmed may list them again (separate docs follow-up, not here).
- verdicts: decider-compat-risk: approve — all six exist without docstring, no __doc__ consumer affected; decider-triage: approve (fresh instance) — about 30-50 lines in 4 files
- status: done — PR #14 merged (auto: low risk, approved by decider-compat-risk, decider-triage, reviewer approve, 51 lines, no tests/UI/API)

## T-pymodaq_utils-010 Add the three missing check_plugin codes to the codes table
- scope: docs   specialty: docs   risk: low
- files: `docs/src/developer_folder/instrument_plugins.rst:144-180` (codes table)
- constraints: only PMQ100 (pyproject.toml cannot be parsed, rules.py:307; package not found, rules.py:806), PMQ200 (syntax error while scanning for todos, rules.py:413), PMQ300 (syntax error in an instrument/extension module, rules.py:509, 703). The other seven codes in the advisor list are already covered by range rows (PMQ101-3, 104-6, 304-6, 330-1): do not split or repeat them. Do not touch legacy_to_current.rst. Wording checked against rules.py messages.
- verdicts: decider-compat-risk: approve — narrowed to 3 codes, docs only; decider-triage: approve — fits one PR (originally counted 10 codes, narrowed after compat-risk)
- status: done — PR #15 merged (auto: low risk, approved by decider-compat-risk, decider-triage, reviewer approve, 3 lines, no tests/UI/API)

## T-pymodaq_utils-011 packages.get_entrypoints delegates to utils.get_entrypoints
- scope: pymodaq_utils   specialty: refactor   risk: medium
- files: `packages.py:159-179`, `utils.py:762-784`
- constraints: bodies are NOT identical: utils version returns a `list`, packages version returns `EntryPoints` (supports `.names`, `.select()`, lookup by name). Delegate packages -> utils only (never the reverse; callers in optimizers_base/models.py:211 and scanner/utils.py:50 rely on the list). Keep both public names; state the return-type change in the docstring and commit; compat-risk finds a `deprecation_msg` justified, or the alternative is to leave it. Do not edit the three monkeypatch tests (models_discovery_test.py:45,54, plugin_configs_test.py:43). Use a function-local import. Run both Qt bindings + layering test. External plugin use unverified.
- verdicts: decider-compat-risk: approve as proposed — return type changes on a public name; decider-triage (fresh): approve — no import cycle
- status: blocked — review: packages.get_entrypoints now delegates to pymodaq_utils.utils.get_entrypoints, so it returns a list instead of EntryPoints and emits a DeprecationWarning; no in

## Dropped (triage)
- B006 `array_manipulation.py:151`, `math_utils.py:616`: read-only defaults; `utils.py:464/482/518` already in T-005.
- mysocket.py duplicate (`mysocket.py:54-67` vs `serialize/mysocket.py:67-80`): needs a shim, low value.
- mechanical ruff fixes (B007, F541, E703, SIM*, E741, abstract.py:12): rule 5 and earlier plan dropped them.
- B024 ObjectFactory: noqa only, too small for a PR. jscpd math_utils/scaffold: 1.9% duplication.
- radon refactors (rules.py, Config.__call__ C(19)): need characterisation tests, staged plan, not a task.
- Config.__del__ + atexit both save(): low value, unmeasured.
- False positives: safe_pickle.py:53 pid, `__init__.py:36` F401, serialize/{factory,serializer}.py:3 F401, serializer_legacy.py:13, vulture 60-79% (public API).
- Outside this scope, to file as findings: PMQ316 translation absent from legacy_to_current.rst (generator limitation); `DataToExportEnumerations` in docs/src/api/utility_api/data_management.rst (pymodaq_data scope); `pymodaq_plugins_utils.hardware` in hardware_discovery.rst unverifiable.
