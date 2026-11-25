# Consortium status — generated 2026-11-25 07:37 by `scripts/status.py`

Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.

## Now
- `dev_agent` at `6ca67182f`; 283 commits ahead of upstream/dev (42 files changed, 714 insertions(+), 193 deletions(-))
- today: runs 3/20, specialist_runs 2/10, prs_opened 0/6, reviews 1/10; outcomes: ok 3
- last /usage reading: 2026-11-24T19:40:03.004000+00:00  session 24% (resets Nov 24, 10:20pm (Europe/Paris))  week 30% (resets Nov 29, 12am (Europe/Paris))
- next cycle step: `merge`

## Needs you
- grill pending: **config-reconcile** (pymodaq_utils) — answer with `/optimize-grill config-reconcile`
- **T-pymodaq_utils-M11** — done — PR #17 open, awaiting the human: registry risk is medium; plan risk is medium; a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; touches tests: packages/p
- **T-pymodaq_utils-006** — done — PR #18 open, awaiting the human: touches tests: packages/pymodaq_utils/tests/config_test.py
- **T-pymodaq_utils-007** — done — PR #24 open, awaiting the human: registry risk is medium; plan risk is medium; a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; reviewer: public_api yes;
- **T-pymodaq_utils-008** — done — PR #19 open, awaiting the human: a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; touches tests: packages/pymodaq_utils/tests/config_test.py
- **T-pymodaq_utils-011** — done — PR #25 open, awaiting the human: registry risk is medium; plan risk is medium; reviewer: public_api yes; touches tests: packages/pymodaq_utils/tests/packages_test.py
- **T-pymodaq_data-001** — done — PR #16 open, awaiting the human: a decider vetoed or blocked it in the plan
- **T-pymodaq_utils-013** — done — PR #23 open, awaiting the human: registry risk is medium; plan risk is medium; touches tests: packages/pymodaq_utils/tests/config_test.py, packages/pymodaq_utils/tests/conftest.py
- blocked: **T-pymodaq_utils-M06** — blocked — pymodaq test scope hangs (extension_loading_test::test_load[Scanner]) on both Qt backends and on the base commit, so qt-backend checks cannot be recorded; code and utils tests are fine

## In flight
- `agent/pymodaq_utils/test-quality/2026-11-25` (T-pymodaq_utils-014, risk low): pushed, waiting for /optimize-merge

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
- [pymodaq_utils] task.py start (port-on-conflict path) writes registry.py on dev_agent then switches to the new branch with registry.jsonl uncommitted; checks refuses 
- [pymodaq_utils] GlobalConfig()('utils', ...) reads through BaseConfig.__getitem__, so the singular/plural fallback in Config.__call__ (backend/debug_level/dynamic) ne
- [pymodaq_utils] docstring says it is raised only for a missing key path; set_logger now also raises it for a wrong value type
- [pymodaq_utils] Utils suite prints 6 '--- Logging error ---' blocks (Not saving config utils under pytest)

## Recent runs
| run | command | outcome | min | out tok | note |
|---|---|---|---|---|---|
| 2026-11-24-merge-T-pymodaq_utils-013-r1 | optimize-merge | ok | 7.1 | 10106 | T-pymodaq_utils-013: done — PR #23 open, awaiting the human: registry  |
| 2026-11-24-run-T-pymodaq_utils-007-r1 | optimize-run | ok | 2.6 | 6482 | rework r1: real-config test, pytest.raises, unused import sys removed; |
| 2026-11-24-merge-T-pymodaq_utils-007-r2 | optimize-merge | ok | 3.1 | 9176 | T-pymodaq_utils-007: blocked — review: set_logger now raises ConfigErr |
| 2026-11-24-run-T-pymodaq_utils-007-r2 | optimize-run | ok | 1.3 | 3655 | rework r2: logger test builds a real config instead of patching getite |
| 2026-11-24-merge-T-pymodaq_utils-007-r3 | optimize-merge | ok | 6.3 | 6492 | T-pymodaq_utils-007: done — PR #24 open, awaiting the human: registry  |
| 2026-11-24-run-T-pymodaq_utils-011-r2 | optimize-run | ok | 1.5 | 4619 | rework r2: test, deprecated version, unused import |
| 2026-11-24-merge-T-pymodaq_utils-011-r3 | optimize-merge | ok | 5.9 | 5902 | T-pymodaq_utils-011: done — PR #25 open, awaiting the human: registry  |
| 2026-11-25-run-T-pymodaq_utils-014 | optimize-run | ok | 2.7 | 4482 | test for ConfigError handler; handler is at __init__.py:40-41 |
| 2026-11-25-merge-T-pymodaq_utils-014-r1 | optimize-merge | ok | 2.6 | 8513 | T-pymodaq_utils-014: blocked — review: Adds a test that a ConfigError  |
| 2026-11-25-run-T-pymodaq_utils-014-r1 | optimize-run | ok | 1.3 | 3278 | rework: CONFIG assertion made non-vacuous (delattr before reload), vac |

## Done so far
- tasks done: 28; PRs merged into dev_agent: 22
