# Consortium status — generated 2026-11-24 22:14 by `scripts/status.py`

Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.

## Now
- `dev_agent` at `fa3e04880`; 244 commits ahead of upstream/dev (40 files changed, 652 insertions(+), 174 deletions(-))
- today: runs 12/20, specialist_runs 6/10, prs_opened 4/6, reviews 6/10; outcomes: ok 11, failed 1
- last /usage reading: 2026-11-24T19:40:03.004000+00:00  session 24% (resets Nov 24, 10:20pm (Europe/Paris))  week 30% (resets Nov 29, 12am (Europe/Paris))
- next cycle step: `run T-pymodaq_utils-007 .agents/plans/2026-11-19-pymodaq_utils-r2.md`

## Needs you
- grill pending: **config-reconcile** (pymodaq_utils) — answer with `/optimize-grill config-reconcile`
- **T-pymodaq_utils-M11** — done — PR #17 open, awaiting the human: registry risk is medium; plan risk is medium; a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; touches tests: packages/p
- **T-pymodaq_utils-006** — done — PR #18 open, awaiting the human: touches tests: packages/pymodaq_utils/tests/config_test.py
- **T-pymodaq_utils-008** — done — PR #19 open, awaiting the human: a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; touches tests: packages/pymodaq_utils/tests/config_test.py
- **T-pymodaq_data-001** — done — PR #16 open, awaiting the human: a decider vetoed or blocked it in the plan
- **T-pymodaq_utils-013** — done — PR #23 open, awaiting the human: registry risk is medium; plan risk is medium; touches tests: packages/pymodaq_utils/tests/config_test.py, packages/pymodaq_utils/tests/conftest.py
- blocked: **T-pymodaq_utils-M06** — blocked — pymodaq test scope hangs (extension_loading_test::test_load[Scanner]) on both Qt backends and on the base commit, so qt-backend checks cannot be recorded; code and utils tests are fine
- blocked: **T-pymodaq_utils-007** — blocked — review: set_logger now raises ConfigError instead of calling sys.exit on a non-list debug_level, and the package import prints its message; the test must use a real con
- blocked: **T-pymodaq_utils-011** — blocked — review: packages.get_entrypoints now delegates to pymodaq_utils.utils.get_entrypoints, so it returns a list instead of EntryPoints and emits a DeprecationWarning; no in
- blocked: **T-pymodaq_utils-014** — blocked — premise false on dev_agent (no ConfigError handler in __init__.py; likely on an unmerged T-007 branch). Rewrite the finding against the `except Exception` fallbacks (reload with a patched GlobalConfig that raises) or drop.

## In flight
- T-pymodaq_utils-007 set_logger must not kill the importing process — blocked — review: set_logger now raises ConfigError instead of calling sys.exit on a non-list debug_level, and the package import prints its message; the test must use a real con
- T-pymodaq_utils-011 packages.get_entrypoints delegates to utils.get_entrypoints — blocked — review: packages.get_entrypoints now delegates to pymodaq_utils.utils.get_entrypoints, so it returns a list instead of EntryPoints and emits a DeprecationWarning; no in

## Open findings (go to the next /optimize-plan of their scope)
- [pymodaq] CI tests-pymodaq.yml tests (ubuntu-latest, pyside6): crash (Fatal Python error: Segmentation), also on upstream/dev
- [pymodaq_data] numpy_func.py:47 returns NotImplementedError instead of raising/returning NotImplemented
- [pymodaq_data] Unverified ruff bug-risk items: B007 loop vars, B018 data.py:1718, F811 append data.py:4226/4241, backends.py:345 unreachable, hyperspy.py:57 data_arr
- [pymodaq_data] numpy_func.py:47 returns NotImplementedError instead of raising it
- [pymodaq_data] data.py:4225 and :4240 redefine append (F811)
- [pymodaq_data] exporters/hyperspy.py:57 assigns data_array, never used (F841)
- [pymodaq] packages/pymodaq tests hang at extension_loading_test.py::TestExtensions::test_load[Scanner] (offscreen, pyqt6 and pyside6, also on base)
- [pymodaq] packages/pymodaq pytest under PYTEST_QT_API=pyqt6 stalls (2% CPU, no end after 20+ min, 3 attempts) during /optimize-merge checks
- [pymodaq] pymodaq suite red on both Qt backends after rebase: pyqt6 state_manager_test::test_non_blocking fails, pyside6 aborts (core dump)
- [pymodaq_utils] Reconcile config files with the template at load (scalar<->list, retype reset, new default follows untouched keys, migrations + snapshot, backup first
- [pymodaq] test_required_config_entries asserts the removed key viewer_in_thread; passes only through a leaked value in the real ~/.pymodaq, fails with a fresh H
- [pymodaq] TestWithSubEntries::test_non_blocking and test_blocking_without_blocking_the_caller[False] fail intermittently on plain dev_agent (3 of 5 runs, pyqt6,
- [agents] A merge run that ends blocked before decide/gate cannot be closed (merge.py close: 'nothing decided yet'), so it gets no ledger line: both M12 runs on
- [agents] task.py checks waited ~20 min per attempt on a hung pytest (2% CPU) and the agent retried 3 times (~60 min) without a stack dump; add per-test timeout
- [agents] No notion of known-flaky tests: a flaky pyqt6 test (state_manager_test, 3 of 5 plain dev_agent runs) and the random pyside6 abort block merges as CI r
- [agents] The merge agent filed a new finding (pyqt6-suite-stalls-2026-11-23, blamed Xvfb) instead of linking the existing M06 hang finding; findings add should
- [agents] findings.py add only accepts ci-upstream/review/run/plugin, and /optimize-research does not file its proposed tasks as findings, so research notes nev
- [agents] The headless merge step started the pyqt6 check in the background and ended its turn ('I'll wait for the completion notice'); step.py stops at the fir
- [agents] Tool tasks cannot pass merge_gate lint: task.py start names them agent/<pkg>/tool/..., plan says agent-tool/<name>, and lint refuses .agents/ files
- [agents] status.py next ranks a rework after fresh tasks, but a fresh task that depends on the blocked one (T-013 on T-012) is picked and refused: the wheel st
- [pymodaq_utils] At pytest exit, save() guard logging and CustomConfig atexit lambdas emit 'I/O operation on closed file' / get_set_path traceback
- [pymodaq_utils] test_get_set_config_dir and TestCopy.test_copy_default still use the real config folders
- [pymodaq_utils] the full config_test.py run still writes test.toml into the real ~/.pymodaq/config (likely TestCopy.test_copy_default/test_copy_source; which one unve
- [pymodaq_utils] "--- Logging error ---" printed at interpreter exit for the 'Not saving config' warning (stream closed; unverified whether it also appears on dev_agen

## Recent runs
| run | command | outcome | min | out tok | note |
|---|---|---|---|---|---|
| 2026-11-24-merge-T-pymodaq_utils-M12-r1 | optimize-merge | ok | 42.5 | 6237 | T-pymodaq_utils-M12: done — PR #20 open, awaiting the human: touches t |
| 2026-11-24-merge-T-pymodaq_utils-015-r1 | optimize-merge | ok | 6.4 | 4722 | T-pymodaq_utils-015: done — PR #21 merged (auto: low risk, approved by |
| 2026-11-24-run-T-pymodaq_utils-012 | optimize-run | ok | 10.2 | 9254 | PYMODAQ_CONFIG_DIR override + pytest save guard; 340 tests both backen |
| 2026-11-24-merge-T-pymodaq_utils-012-r1 | optimize-merge | ok | 4.1 | 13994 | T-pymodaq_utils-012: blocked — review: Adds a PYMODAQ_CONFIG_DIR overr |
| 2026-11-24-run-T-pymodaq_utils-012-r1 | optimize-run | ok | 1.8 | 7090 | rework r1: 5 review findings fixed; narrow guard (config_path inside P |
| 2026-11-24-merge-T-pymodaq_utils-012-r2 | optimize-merge | ok | 3.2 | 10327 | T-pymodaq_utils-012: blocked — review: Adds a PYMODAQ_CONFIG_DIR overr |
| 2026-11-24-run-T-pymodaq_utils-012-r2 | optimize-run | ok | 2.3 | 5085 | rework r3: atexit leak closed, exit-path test rewritten, docstring fix |
| 2026-11-24-merge-T-pymodaq_utils-012-r3 | optimize-merge | ok | 4.3 | 12126 | T-pymodaq_utils-012: blocked — PR CI unavailable: no checks found on P |
| 2026-11-24-run-T-pymodaq_utils-013 | optimize-run | ok | 11.5 | 7411 | conftest isolated_config_dir fixture; test_load_system_config isolated |
| 2026-11-24-merge-T-pymodaq_utils-013-r1 | optimize-merge | ok | 7.1 | 10106 | T-pymodaq_utils-013: done — PR #23 open, awaiting the human: registry  |

## Done so far
- tasks done: 25; PRs merged into dev_agent: 19
