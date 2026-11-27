# /optimize-plan pymodaq — 2026-11-28 — advisor opinions
scan: .agents/scans/pymodaq-f140d199ab62.md (sha256 3c1399b65724a4bc8ed3b8bdbb261537af5e3e4f15c8ff4c9081afea1766a71c)
base commit: 88f0fdccf   mode: run

## Open findings (findings.py list --scope pymodaq --status open)
```
open     pymodaq            seen 3x  CI tests-pymodaq.yml tests (ubuntu-latest, pyside6): crash (Fatal Python error: Segmentation), also on upstream/dev
         key: tests-pymodaq.yml|tests (ubuntu-latest, pyside6)|crash
         evidence: https://github.com/Ashwolaa/PyMoDAQ/actions/runs/44544135928, https://github.com/PyMoDAQ/PyMoDAQ/actions/runs/44539882823, https://github.com/Ashwolaa/PyMoDAQ/actions/runs/45402418737
open     pymodaq            seen 1x  packages/pymodaq tests hang at extension_loading_test.py::TestExtensions::test_load[Scanner] (offscreen, pyqt6 and pyside6, also on base)
         key: pymodaq-scanner-ext-load-hang
         evidence: timeout 120 pytest tests/extensions/extension_loading_test.py -k Scanner -> rc 124 on base commit and on M06 branch; task.py checks --backend runs the whole pymodaq scope whenever packages/pymodaq/pyproject.toml is touched and never returns
open     pymodaq            seen 1x  packages/pymodaq pytest under PYTEST_QT_API=pyqt6 stalls (2% CPU, no end after 20+ min, 3 attempts) during /optimize-merge checks
         key: pyqt6-suite-stalls-2026-11-23
         evidence: run 2026-11-23-merge-T-pymodaq_utils-M12-r1: 16% of tests after 19 min, process in do_sys_poll, 25s CPU in 10 min; pytest-xvfb warns Xvfb not found; same suite gave 881 passed on 2026-11-22
open     pymodaq            seen 1x  pymodaq suite red on both Qt backends after rebase: pyqt6 state_manager_test::test_non_blocking fails, pyside6 aborts (core dump)
         key: pymodaq-suite-backend-failures-2026-11-23
         evidence: pyqt6: 1 failed 882 passed; pyside6: pytest Aborted (core dumped) with no failing id; branch only adds a 10-line test; probably the known GC/QThread crash and a flaky timing test (unverified)
open     pymodaq            seen 1x  test_required_config_entries asserts the removed key viewer_in_thread; passes only through a leaked value in the real ~/.pymodaq, fails with a fresh HOME. Same for daq_viewer_test.py:34
         key: tests/utils/config_test.py:test_required_config_entries|stale viewer_in_thread
         evidence: .agents/research/config-schema.md (prototype agent-rd/config-schema @272b75d0e) (verified with fresh HOME on dev_agent)
open     pymodaq            seen 1x  TestWithSubEntries::test_non_blocking and test_blocking_without_blocking_the_caller[False] fail intermittently on plain dev_agent (3 of 5 runs, pyqt6, ~45 s per run); blocked the M12 merge as a false CI red
         key: state_manager_test.py:TestWithSubEntries|flaky timing
         evidence: run 2026-11-23-merge-T-pymodaq_utils-M12-r2; manual 5 reruns on dev_agent 2026-11-23
open     pymodaq            seen 1x  Enable scripting tooltip says it also runs a Coordinator; handler only calls connect_leco
         key: enable-scripting-tooltip-coordinator
         evidence: pymodaq/utils/shared_ui.py:46
```

## Grill directions in force (answered)
- config-isolation: PYMODAQ_CONFIG_DIR override + root conftest tmp dir + Config.save guard under pytest; fork only; no h5manager UI change.
- config-reconcile: reconcile-on-load for core configs only (backup, atomic write); fork only until config-isolation merged.

## advisor-quality
1. control_modules/move_utility_classes.py:532 and :962 DAQ_Move_base.ini_stage_init defined twice; second overrides first (type: ignore[no-redef]). V5 E2 R medium. Owner must say which body is live.
2. extensions/sequencer/utilities/states.py:19 direct PyQt5 import (hard rule 6). V4 E1 R low.
3. B012 return in finally: control_modules/ui_utils.py:374, utils/scanner/utils.py:45, sequencer/utilities/choice_models/factory.py:29, element_factory.py:64. V4 E2 R medium.
4. B023 loop-variable closure: sequencer/utilities/sequencer/model_view.py:546. V3 E1 R low; confirm bug first.
5. E722 bare except: extensions/data_mixer/data_mixer.py:188, daq_logger/daq_logger_legacy.py:448,465. V3 E1 R low.
6. B006 mutable defaults ~10 sites (utils/managers/batchscan_manager.py:37,229, pid_controller.py:784-785). V3 E2 R medium; None sentinel, public signatures.
7. Duplicate dict key 'removable' utils/managers/remote_manager.py:80,129,132 (same value). V1.
8. F811 register_scanners imported twice pymodaq/__init__.py:29,52. V1.
9. F841 unused e/locals ~60. V1; only in already-touched files.
FALSE POSITIVES (do not act): utils/daq_utils.py:9 backcompat re-exports; utils/gui_utils/__init__.py F401 shim; utils/config.py:7; utils/data.py:12 NavAxis (legacy_to_current.rst:308); daq_xDviewer_LECODirector.py:11 noqa side-effect import; package __init__ re-exports; yaml_utils.py:5 indentless; leco_director.py:144,163 B018 (unverified); jscpd resources/experiment_default.xml; vulture 60-79%; style counts UP006/UP007/I001 (would exceed 300-line cap).
DEFER: radon DAQ_Move.thread_status E(32), DashBoard.pygame_loop D(23) (live).

## advisor-performance
1. processEvents worker-loop pumps optimizers_base/optimizer.py:287, pid/pid_controller.py:956. V4 E3 R medium (planned event-driven replacement).
2. processEvents in teardown control_modules/utils.py:867,905,918 then wait(5000)+terminate() 922-923. V4 E2 R high.
3. processEvents construction/loading: daq_viewer.py:974,1276; daq_viewer_ui/ui_base.py:352,355; dashboard.py:873; modules_manager.py:633,966; scan_manager.py:205,256. V3 E2 R medium; overlaps owner branch cleanup/reduce-process-events.
4. processEvents helpers scan_selector.py:422,426,465; scanner.py:252; svg_viewer2D.py:45. V2 E1 low.
5. Test harness pumps plugin_testing/harness.py:63, extension_testing.py:36,79: keep (false positive).
6. Raw-string ThreadCommand not in any enum: extensions/scan/daq_scan.py (dispatch 1470-1479). V4 E2 R low-medium.
7. Same in pid_controller.py (dispatch 863-884); suggest PIDCommand StrEnum. 
8. leco/pymodaq_listener.py:337 'disconnected', daq_move.py:772 'check_position'. V2.
9. Raw strings matching enum members: daq_viewer.py:1265 'grab', :1290 'grab_stopped'; move_utility_classes.py:673,679,682 'outofbounds'. V3 E1 R low.
10. "Update_Status" case mismatch vs ThreadStatus.UPDATE_STATUS='update_status' (control_modules/utils.py:415,422; daq_move_PID.py:144; daq_scan.py:1063). V4 E1; plugins may emit legacy string -> shim + deprecation_msg.
11. daq_move.py:718 thread_status E(32), dispatch table. V4 E4 R medium.
12-13. Unused ThreadCommand/ThreadStatus imports (re-exports, false positive); ui_base.py:27 F811 duplicate import V1.

## advisor-docs
- No doc findings in scan. Only jscpd clone extensions/adaptive_optim/help.md:5-11 == extensions/bayesian/help.md:5-11 (7 lines). llms.txt links resolve to existing rst. No sphinx build run.

## advisor-compat
1. docs/src/developer_folder/legacy_to_current.rst out of sync: missing pymodaq_utils.packages get_entrypoints entry (deprecated at packages.py:179, now returns list). 9-line diff from generator page(). Fix by regenerating with python docs/legacy_to_current.py (hard rule 3).
2. check_plugin PMQ302 names (_epsilon, stage_names, axis_names; plugin_tools/rules.py:572-580) absent from legacy page; generator reads only deprecation_msg calls. Generator scope gap.
3. Entry-point group pymodaq.managers consumed (extra_managers.py:23, dashboard.py:172) but absent from checks.py:46-48 and hatch_build_plugins.py/setup_plugin.py generators. Intent unverified.
Checked OK: entry-point groups in daq_utils.py:35-36 match generators; check_plugin mock exit 0; vulture 60-79% may be public API.

## advisor-uxui (no renders; rendering unverified)
1. control_modules/daq_move_ui/ui_base.py:181,186 hardcoded lightgreen/lightcoral backgrounds + black text: hard rule 6 (StatusPalette). V4 E2 R medium.
2. launcher/launcher.py:189,312 color: white separators. V2 E1 low.
3. utils/chrono_timer.py:66,186 Window palette QColor(0,0,0). V2, maybe intentional.
4. sequencer/utilities/states.py:15,19 direct PyQt6/PyQt5 imports (hard rule 6). V3 E2 R medium; qtpy QtStateMachine support unverified.
5. extensions/scan/daq_scan.py:721-733 inline stylesheets via color_to_rgba; status meaning unverified.
6. Silent except e: daq_move_ui/ui_base.py:448, daq_viewer_ui/ui_base.py:298, dashboard.py:799. V3 E1 R medium.
7. Unused qt_themes imports (control_modules/ui_utils.py:6, daq_scan.py:16, sequencer/.../scanner.py:19). V2.
8. Unused create_font/create_icon control_modules/ui_utils.py:12 (plugin use? hard rule 1). V2 R medium.
9. gui_utils/__init__.py re-exports: false positive.
10. 27 setToolTip; wording unverified.
11. dashboard.py pygame_loop D(23) quality, not UX.

## decider-triage (kept 11, 1 GRILL)
Paths under packages/pymodaq/src/pymodaq/ unless noted.
- T-pymodaq-001 Remove dead first DAQ_Move_base.ini_stage_init body. hygiene, medium. control_modules/move_utility_classes.py:532 (dead), :962 (live: deprecation shim calling ini_controller_init, plugin_base.py:110). tests no, API no.
- T-pymodaq-002 Route sequencer QStateMachine imports through qtpy (hard rule 6). hygiene, low-medium. extensions/sequencer/utilities/states.py:15,19. Check qtpy.QtStateMachine under PyQt6.
- T-pymodaq-003 Fix B012 return-in-finally. hygiene, medium. control_modules/ui_utils.py:374, utils/scanner/utils.py:45, extensions/sequencer/utilities/choice_models/factory.py:29, extensions/sequencer/utilities/element_factory.py:64.
- T-pymodaq-004 Narrow bare/silent excepts and log. hygiene, low. extensions/data_mixer/data_mixer.py:188, extensions/daq_logger/daq_logger_legacy.py:448,465, control_modules/daq_move_ui/ui_base.py:448, control_modules/daq_viewer_ui/ui_base.py:298, dashboard.py:799 (last three unverified).
- T-pymodaq-005 Small cleanups: duplicate 'removable' key, second register_scanners import, duplicate ThreadCommand import. hygiene, low. utils/managers/remote_manager.py:80,129,132, __init__.py:29,52, control_modules/daq_viewer_ui/ui_base.py:27.
- T-pymodaq-006 lightgreen/lightcoral -> StatusPalette (hard rule 6). uiux, medium. control_modules/daq_move_ui/ui_base.py:181,186.
- T-pymodaq-007 Fix Enable scripting tooltip (says Coordinator; handler only connect_leco). uiux, low. utils/shared_ui.py:46 (handler :64-66). finding enable-scripting-tooltip-coordinator.
- T-pymodaq-008 TestWithSubEntries: wait on signals (qtbot.waitSignal/waitUntil) not fixed timing, no assertion weakened. test-quality, medium. packages/pymodaq/tests/.../state_manager_test.py. finding state_manager_test.py:TestWithSubEntries|flaky timing (+ pyqt6 half of pymodaq-suite-backend-failures-2026-11-23). tests yes.
- T-pymodaq-009 Regenerate legacy_to_current.rst via python docs/legacy_to_current.py (get_entrypoints entry). docs, low.
- T-pymodaq-010 Raw strings -> matching enum members. refactor, low. control_modules/daq_viewer.py:1265 'grab', :1290 'grab_stopped'; control_modules/move_utility_classes.py:673,679,682 'outofbounds'. Overlaps T-001 file.
- T-pymodaq-011 B006 mutable defaults -> None sentinel. refactor, medium, API yes (signatures). utils/managers/batchscan_manager.py:37,229, extensions/pid/pid_controller.py:784-785.
Findings: GC pyside6 crash dropped (upstream too, owner branch fix/tests-gc-main-thread); scanner-ext-load-hang dropped (root cause unknown, needs rd-researcher); pyqt6-suite-stalls merged into the hang investigation (dropped with it); suite-backend-failures: pyqt6 half -> T-008, pyside6 half = GC crash; stale viewer_in_thread dropped (already fixed, no occurrence under packages/); flaky timing -> T-008; tooltip -> T-007.
Not kept: processEvents (owner branch / perf-threading not enabled / high risk), B023 unconfirmed, Update_Status (plugins), PIDCommand/thread_status refactor (API/too large), help.md clone, PMQ302 generator gap (tooling), colours/unused imports/F841 (low value or plugin API).
GRILL pymodaq-managers-entrypoint: support or deprecate pymodaq.managers group -> .agents/grill/pymodaq-managers-entrypoint.md (registered).

## Decisioners (step 6)
- T-001 compat approve (low) / triage2 approve (low) -> approved
- T-002 compat veto / triage2 veto (qtpy QtStateMachine raises under PyQt5/6) -> blocked
- T-003 compat approve (medium) / triage2 approve (medium) -> proposed
- T-004 compat approve / triage2 approve, scope cut to 3 bare excepts -> approved
- T-005 compat approve / triage2 approve; ThreadCommand dup is in daq_move_ui/ui_base.py:27 -> approved
- T-006 compat veto / triage2 veto (not status colours) -> blocked
- T-007 compat approve / triage2 approve -> proposed (UI)
- T-008 compat approve (diagnose first) / test-change veto -> blocked (veto holder; no second round)
- T-009 compat approve / triage2 approve -> approved
- T-010 compat approve / triage2 approve -> approved
- T-011 compat approve (low) / triage2 approve (low) -> proposed (public signatures)
- decider-arbiter T-001 vs T-010: separate PRs, T-001 first, T-010 locates sites by content after T-001 merges.
Findings filed: pid_controller.py:PIDRunner|default setpoints IndexError (run).
