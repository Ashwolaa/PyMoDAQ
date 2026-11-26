# Consortium status — generated 2026-11-26 07:58 by `scripts/status.py`

Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.

## Now
- `dev_agent` at `47611e3df`; 327 commits ahead of upstream/dev (49 files changed, 807 insertions(+), 246 deletions(-))
- today: runs 1/20, specialist_runs 0/10, prs_opened 1/6, reviews 1/10; outcomes: ok 1
- last /usage reading: 2026-11-26T06:58:54.808000+00:00  session 6% (resets Nov 26, 12:50pm (Europe/Paris))  week 52% (resets Nov 29, 12am (Europe/Paris))
- next cycle step: `plan pymodaq_gui`

## Needs you
- grill pending: **config-reconcile** (pymodaq_utils) — answer with `/optimize-grill config-reconcile`
- blocked: **T-pymodaq_utils-M06** — blocked — pymodaq test scope hangs (extension_loading_test::test_load[Scanner]) on both Qt backends and on the base commit, so qt-backend checks cannot be recorded; code and utils tests are fine

## In flight
- nothing queued

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
- [pymodaq_scripting] No autodoc page for pymodaq_scripting: :class:/:mod: targets in scripting docs do not resolve
- [pymodaq] Enable scripting tooltip says it also runs a Coordinator; handler only calls connect_leco

## Recent runs
| run | command | outcome | min | out tok | note |
|---|---|---|---|---|---|
| 2026-11-25-merge-T-pymodaq_utils-014-r2 | optimize-merge | ok | 3.3 | 5840 | T-pymodaq_utils-014: blocked — review: Adds a test that a ConfigError  |
| 2026-11-25-run-T-pymodaq_utils-014-r2 | optimize-run | ok | 2.9 | 3698 | rework r2: assert CONFIG before the restoring reload |
| 2026-11-25-merge-T-pymodaq_utils-014-r3 | optimize-merge | ok | 6.7 | 5425 | T-pymodaq_utils-014: done — PR #26 open, awaiting the human: a decider |
| plan-pymodaq_scripting-20261125 | optimize-plan | ok | 7.3 | 43748 |  |
| 2026-11-25-run-T-pymodaq_scripting-001 | optimize-run | ok | 0.8 | 3559 | hygiene: __all__, unused imports, .keys() |
| 2026-11-25-merge-T-pymodaq_scripting-001-r1 | optimize-merge | ok | 5.7 | 5603 | T-pymodaq_scripting-001: done — PR #27 merged (auto: low risk, approve |
| 2026-11-25-run-T-pymodaq_scripting-002 | optimize-run | ok | 2.1 | 12314 | docs only, 101 lines; make_component_leco_available.rst:584-610 left o |
| 2026-11-25-merge-T-pymodaq_scripting-002-r1 | optimize-merge | ok | 2.6 | 8818 | T-pymodaq_scripting-002: blocked — review: Points the scripting docs t |
| 2026-11-25-run-T-pymodaq_scripting-002-r1 | optimize-run | ok | 1.1 | 4216 | rework r1: 3 review fixes applied (leco import + :class: targets, get_ |
| 2026-11-26-merge-T-pymodaq_scripting-002-r2 | optimize-merge | ok | 5.0 | 6689 | T-pymodaq_scripting-002: done — PR #28 merged (auto: low risk, approve |

## Done so far
- tasks done: 30; PRs merged into dev_agent: 25
