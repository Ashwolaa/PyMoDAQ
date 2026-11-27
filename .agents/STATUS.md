# Consortium status — generated 2026-11-28 00:18 by `scripts/status.py`

Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.

## Now
- `dev_agent` at `790334ecd`; 375 commits ahead of upstream/dev (66 files changed, 931 insertions(+), 274 deletions(-))
- today: runs 2/20, specialist_runs 0/10, prs_opened 1/6, reviews 1/10; outcomes: ok 2
- last /usage reading: 2026-11-27T23:17:57.450000+00:00  session 82% (resets Nov 28, 2am (Europe/Paris))  week 24% (resets Nov 29, 12am (Europe/Paris))
- next cycle step: `run T-pymodaq-001 .agents/plans/2026-11-28-pymodaq.md`

## Needs you
- approve or drop **T-pymodaq-003** Move return out of finally (B012) in four plugin-discovery helpers — proposed (`.agents/plans/2026-11-28-pymodaq.md`)
- approve or drop **T-pymodaq-007** Fix the "Enable scripting" tooltip — proposed (`.agents/plans/2026-11-28-pymodaq.md`)
- approve or drop **T-pymodaq-011** None sentinel for mutable default arguments — proposed (`.agents/plans/2026-11-28-pymodaq.md`)
- grill pending: **pymodaq-managers-entrypoint** (pymodaq) — answer with `/optimize-grill pymodaq-managers-entrypoint`
- **T-pymodaq_gui-001** — done — PR #30 open, awaiting the human: touches tests: packages/pymodaq_gui/tests/parameter_test/param_ioxml_mutable_default_test.py, packages/pymodaq_gui/tests/utils/h5tree_to_qtree_test.py; touches
- **T-pymodaq_gui-002** — done — PR #31 open, awaiting the human: touches tests: packages/pymodaq_gui/tests/utils/widgets/pattern_completer_test.py; touches a UI scope: packages/pymodaq_gui/src/pymodaq_gui/utils/widgets/patter
- **T-pymodaq_gui-003** — done — PR #32 open, awaiting the human: registry risk is medium; plan risk is medium; reviewer: public_api yes; touches tests: packages/pymodaq_gui/tests/managers/manager_base_test.py; touches a UI sc
- **T-pymodaq_gui-005** — done — PR #29 open, awaiting the human: touches a UI scope: packages/pymodaq_gui/src/pymodaq_gui/managers/settings/subentries.py, packages/pymodaq_gui/src/pymodaq_gui/parameter/pymodaq_ptypes/pixmap.p
- blocked: **T-pymodaq_utils-M06** — blocked — pymodaq test scope hangs (extension_loading_test::test_load[Scanner]) on both Qt backends and on the base commit, so qt-backend checks cannot be recorded; code and utils tests are fine
- blocked: **T-pymodaq-002** — blocked — vetoed by both: qtpy has no PyQt6 QtStateMachine; owner to confirm states.py as a hard-rule-6 exception
- blocked: **T-pymodaq-006** — blocked — vetoed by both: not status colours; re-triage as a ThemeColor task if wanted
- blocked: **T-pymodaq-008** — blocked — vetoed by decider-test-change: fix as written weakens asserts; re-scope as root-cause task

## In flight
- T-pymodaq-001 Remove the dead first DAQ_Move_base.ini_stage_init body — approved
- T-pymodaq-004 Replace three bare excepts around disconnect calls — approved
- T-pymodaq-005 Remove three duplicate definitions (dict key, imports) — approved
- T-pymodaq-009 Regenerate legacy_to_current.rst — approved
- T-pymodaq-010 Use ThreadStatus enum members instead of raw strings — approved

## Open findings (go to the next /optimize-plan of their scope)
- [pymodaq_data] numpy_func.py:47 returns NotImplementedError instead of raising/returning NotImplemented
- [pymodaq_data] Unverified ruff bug-risk items: B007 loop vars, B018 data.py:1718, F811 append data.py:4226/4241, backends.py:345 unreachable, hyperspy.py:57 data_arr
- [pymodaq_data] numpy_func.py:47 returns NotImplementedError instead of raising it
- [pymodaq_data] data.py:4225 and :4240 redefine append (F811)
- [pymodaq_data] exporters/hyperspy.py:57 assigns data_array, never used (F841)
- [pymodaq_utils] Reconcile config files with the template at load (scalar<->list, retype reset, new default follows untouched keys, migrations + snapshot, backup first
- [agents] A merge run that ends blocked before decide/gate cannot be closed (merge.py close: 'nothing decided yet'), so it gets no ledger line: both M12 runs on
- [agents] task.py checks waited ~20 min per attempt on a hung pytest (2% CPU) and the agent retried 3 times (~60 min) without a stack dump; add per-test timeout
- [agents] No notion of known-flaky tests: a flaky pyqt6 test (state_manager_test, 3 of 5 plain dev_agent runs) and the random pyside6 abort block merges as CI r
- [agents] The merge agent filed a new finding (pyqt6-suite-stalls-2026-11-23, blamed Xvfb) instead of linking the existing M06 hang finding; findings add should
- [agents] findings.py add only accepts ci-upstream/review/run/plugin, and /optimize-research does not file its proposed tasks as findings, so research notes nev
- [agents] The headless merge step started the pyqt6 check in the background and ended its turn ('I'll wait for the completion notice'); step.py stops at the fir
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
- [pymodaq_gui] tests/managers/action_manager_test.py::test_icon_qt fails on base (PyQt6 and PySide6, offscreen)
- [pymodaq_gui] The 6 touched files still have other unused imports (e.g. roi.py LinearRegionItem, Slot; pixmap.py QByteArray, QObject; filter.py QtCore, roi_format),
- [pymodaq_gui] flake8 on pymodaq_gui prints SyntaxWarning invalid escape '\*' at <unknown>:457 (file not identified)
- [pymodaq] PIDRunner with default setpoints=[] raises IndexError at setpoints[ind]

## Recent runs
| run | command | outcome | min | out tok | note |
|---|---|---|---|---|---|
| 2026-11-26-merge-T-pymodaq_gui-005-r1 | optimize-merge | ok | 8.4 | 7983 | T-pymodaq_gui-005: done — PR #29 open, awaiting the human: touches a U |
| 2026-11-26-run-T-pymodaq_gui-001 | optimize-run | ok | 12.8 | 12291 | mutable defaults fixed in 5 files, 2 regression tests; local gui suite |
| 2026-11-27-merge-T-pymodaq_gui-001-r1 | optimize-merge | ok | 8.8 | 8553 | T-pymodaq_gui-001: done — PR #30 open, awaiting the human: touches tes |
| 2026-11-27-run-T-pymodaq_gui-002 | optimize-run | ok | 8.0 | 5843 | qtpy QListView in update_completer_config; word_wrap test fails on PyS |
| 2026-11-27-merge-T-pymodaq_gui-002-r1 | optimize-merge | ok | 9.0 | 6690 | T-pymodaq_gui-002: done — PR #31 open, awaiting the human: touches tes |
| 2026-11-27-run-T-pymodaq_gui-003 | optimize-run | ok | 4.9 | 11641 | .colors element type GlobalColor->QColor (note in PR); screenshots lig |
| 2026-11-27-merge-T-pymodaq_gui-003-r1 | optimize-merge | ok | 7.9 | 8309 | T-pymodaq_gui-003: done — PR #32 open, awaiting the human: registry ri |
| 2026-11-27-run-T-pymodaq_gui-004 | optimize-run | ok | 1.4 | 4960 | jscpd --ignore material_icons resources; 55 agents tests green |
| 2026-11-28-merge-T-pymodaq_gui-004-r1 | optimize-merge | ok | 3.1 | 7116 | T-pymodaq_gui-004: done — PR #33 merged (auto: low risk, approved by d |
| 2026-11-28-plan-pymodaq | optimize-plan | ok | 6.7 | 140567 |  |

## Done so far
- tasks done: 35; PRs merged into dev_agent: 26
