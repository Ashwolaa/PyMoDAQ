# /optimize-plan pymodaq_gui — 2026-11-26 — advisor opinions
scan: .agents/scans/pymodaq_gui-1f84d293f927.md (sha256 15edf186e8681680ef38f8a59a08f98689c8b8bb18f580b6980a478af594f19f)
base commit: e596dd95a   mode: run

## Open findings (findings.py list --scope pymodaq_gui --status open)
(empty output: no open findings)

## advisor-quality
1. viewerND.py:313 and :451 `return` in `finally` swallows exceptions (B012). V4 E2 risk medium. Set navigator_data before try, else UnboundLocalError.
2. B006 mutable defaults: roi.py:361/465/522/533/552, viewer1Dbasic.py:102/172, utils/utils.py:245, ioxml.py:377, saving.py:253, browsing.py:442. V4 E2 medium. Public signatures; use None + default in body.
3. Bare except E722: action_manager.py:363, settings/utils.py:106. V3 E1 low.
4. Unused `e`/locals F841 (~40): ioxml.py:277, viewerND.py:310/412/448, viewer2D.py:1091-1095. V2 E1 low. Only lines already changed (hard rule 5).
5. Dead assignments: image.py:459/463, viewer2D.py:297 parent_image_item, lineout.py:232. V2 E1 low.
6. Unused imports >=90% vulture: tableview.py ColorButton, viewer.py Averaging, viewer0D.py Real, viewerND.py ABCMeta, ioxml.py PARAM_NAMES. V2 E1 low; check re-exports. dock.py DockLabel used by tests/utils/dock_test.py.
7. FALSE POSITIVE action_manager.py:1278-1368 F811: @dispatch overloads. Do not touch.
8. FALSE POSITIVE app_worker.py:27 ModulesManager (TYPE_CHECKING string annotation).
9. Import redefinitions F811: pymodaq_ptypes/__init__.py:17 GroupParameter, settings/subentries.py:15 StrEnum, ioxml.py:12/16, pixmap.py:5-7, roi.py:221, filter.py:20. V2 E1 medium; __init__ re-export may be plugin-visible.
10. Vulture 60-79% (~300): mostly public API false positives. Never delete top-level names without checking legacy_to_current.rst.
11. Radon E(38) plot_utils.py:272 makeAlphaTriangles, D(23) viewerND.py:587 set_data_test. V2 E5 high.
12. jscpd 24% duplication all in resources/material_icons/resources/icons_rounded_{20,40}.py: generated (hard rule 3); exclude folder from jscpd instead. V1 E1.

## advisor-performance (no profiler data in scan; runtime cost unverified)
1. viewer2D.py:1156 processEvents in per-ROI loop of process_roi_lineouts, every frame. V4 E2 medium (re-entrancy).
2. viewer0D.py:398 processEvents in display_data. V3 E1 medium.
3. managers/settings/utils.py:100 processEvents in value_changed before commitData.emit. V3 E1 medium; may flush focus loss.
4. settings_manager.py:111 processEvents + QThread.msleep(0) per entry in _execute_entry. V3 E2 medium.
5. qt_plotters.py:62 processEvents in plot(). V2 E1 low.
6. Demo/__main__ helpers (viewer1D.py 717-900, manager_base.py:779, lcd.py:112, viewer2D.py:1250). V1, leave.
Note: branch cleanup/reduce-process-events (owner's, upstream-bound) likely overlaps 3 and 4.
7. No runtime raw-string ThreadCommand in pymodaq_gui (only examples/saving_loading.py:288-319).
8. Raw-string ThreadCommand heavy in pymodaq scope (out of scope).
9. Cross-thread sites editor/monaco.py:220-221, runner_thread_manager.py:96-100: unverified.
10. QThread.msleep in GUI thread: settings_manager.py:112, manager_base.py:780-781 (demo). V2 E1 low.
Recommendation: measure (pyinstrument) before changing 1-2.

## advisor-docs
No docs-facing findings in scan. llms.txt: 18 links all have .rst sources (existence only). Nothing actionable.

## advisor-compat
1. ROI_select_signal (plotting/data_viewers/base.py:164) deprecated only in a comment: no deprecation_msg, no legacy_to_current entry. PR #1515 (owner's, fix/viewernd-roi-select-signal) touches the same area — unverified whether it changes this signal.
2. saving.py:434-435 set_current_scan_path(create_scan_folder=...) flagged unused by vulture: public kwarg, must stay.
- Vulture 60-79% mostly public-looking; get_external_toolbar_menu used by pymodaq; DataSequential no in-repo caller; tree_change_blocker, compareParameters used by pymodaq.
- check_plugin on pymodaq_plugins_mock OK; mock imports pymodaq_ptypes (GroupParameter, registerParameterType) and parameter.utils.iter_children — none in unused lists.

## advisor-uxui (no renders; visuals unverified)
1. pattern_completer.py:188 direct PyQt6 import in a lazy branch (hard rule 6). V4 E1 low. ImportError on PySide6-only install with word_wrap kwarg. Found by grep, not scan.
2. Status colours outside StatusPalette: manager_base.py:58-94 (darkGreen/darkRed/darkGray), settings_manager.py:288 (green brush). V4 E2 medium (hard rule 6).
3. viewer0D.py:329 literal icon colours #F9A825/#607D8B. V3 E1 low.
4. Hard-coded theme colours: utils/utils.py:129-204, collapsible_widget.py:198-206, image_viewer.py:17. V3 E3 medium.
5. manager_base.py:742 `QListView { outline: none; }` removes focus outline. V3 E1 low.
6. lineout.py:141 ROI `color` read and unused (F841): ROI colour possibly never applied. V3 E2 low.
7. styling.py:300 create_icon C(13). V2 E3 medium.
8. Generated icons_rounded_20/40.py PySide2 fallback imports: generated (hard rule 3).
9. examples/icons.py:3-5 direct PyQt6 imports; other examples F401. V2 E1 low.
10. utils/__init__.py:5,11 and utils/widgets/__init__.py:3,5 re-exports flagged unused: add __all__, never remove.
11. examples/theming_demo.py already uses StatusPalette: model.

## decider-triage (kept 5, no GRILL)
T-pymodaq_gui-001 Fix mutable default arguments (hygiene, low, ~40 lines): utils/utils.py:245 pixmap_items=[] (browsing.py:494 calls h5tree_to_QTree without it; line 298 appends -> shared list grows per browsed file), parameter/ioxml.py:377 params=[] (walk_xml_to_parameter appends at 412), plus h5modules/browsing.py:442, plotting/data_viewers/viewer1Dbasic.py:102,172, plotting/data_viewers/viewer.py:296 (mutation unverified). Default None, build in body, no name/signature-order change. Add regression tests for the two confirmed bugs. Leave roi.py out (PR #1515).
T-pymodaq_gui-002 Use qtpy in pattern_completer (hygiene, low, 1 line + test): utils/widgets/pattern_completer.py:188 `from PyQt6.QtWidgets import QListView` -> qtpy. Hard rule 6.
T-pymodaq_gui-003 Manager status colours via StatusPalette (uiux, medium, ~30 lines): managers/manager_base.py:58-94. Default mapping None->OFF, True->IDLE, False->ERROR (utils/status_palette.py:121-128; ERROR is orange, not darkRed). Not settings_manager.py:288 (not a status). Check overlap with PR #1517/#1523.
T-pymodaq_gui-004 Exclude generated icon resources from jscpd (tool, low): exclude resources/material_icons/resources/icons_rounded_{20,40}.py in the scanner config; no product file change.
T-pymodaq_gui-005 Remove unused and duplicate imports (hygiene, low): duplicates pixmap.py:5-7, managers/settings/subentries.py:15, roi.py:221, filter.py:20; unused tableview.py ColorButton, viewer0D.py Real. Do not touch pymodaq_ptypes/__init__.py, __init__ re-exports, viewerND.py, ioxml.py. Grep pymodaq + plugins for re-exports first.
Dropped: viewerND.py:313/451 return-in-finally (PR #1515 file; plan after merge); all processEvents items (overlap cleanup/reduce-process-events, unmeasured); bare except action_manager.py:363 (PR #1523) and settings/utils.py:106 (next to processEvents); ROI_select_signal deprecation and lineout.py:141 (ROI area, #1515); viewer0D.py:329 icon colours (#1517); unused locals/dead assignments (hard rule 5, little value); radon hotspots (high effort, no bug); vulture 60-79% + create_scan_folder (public API false positives); theme colours and QListView outline (no renders); F811 action_manager/app_worker (false positives); examples (low value).
