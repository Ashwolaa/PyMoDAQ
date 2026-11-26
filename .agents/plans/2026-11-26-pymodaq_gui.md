# Plan: pymodaq_gui — 2026-11-26
base commit: e596dd95a   mode: run

Scan: .agents/scans/pymodaq_gui-1f84d293f927.md (sha256 15edf186e8681680ef38f8a59a08f98689c8b8bb18f580b6980a478af594f19f). Scanners missing: none reported.
Open findings (findings.py list --scope pymodaq_gui --status open): none.
Advisor opinions and triage: .agents/reports/pymodaq_gui/2026-11-26-plan-advisors.md
Owner branches checked for overlap (git diff --stat upstream/dev...): feature/action-manager-groups (#1523) and fix/viewer-legend-click-sync (#1517) touch none of the files below. fix/viewernd-roi-select-signal (#1515) is not in local refs: overlap with roi.py unverified.
Dropped by triage: viewerND.py:313/451 return-in-finally (real bug, PR #1515 file: plan after it merges); processEvents sites (overlap cleanup/reduce-process-events, unmeasured); bare except action_manager.py:363 (#1523) and settings/utils.py:106; ROI_select_signal deprecation and lineout.py:141 unused ROI colour (ROI area, #1515); viewer0D.py:329 icon colours; unused locals/dead assignments (hard rule 5); radon hotspots; vulture 60-79% and create_scan_folder (public API); theme colours and QListView outline (no renders); F811 action_manager @dispatch / app_worker TYPE_CHECKING (false positives); examples.

## T-pymodaq_gui-001 Fix mutable default arguments
- scope: pymodaq_gui   specialty: hygiene
- risk: low
- files: `packages/pymodaq_gui/src/pymodaq_gui/utils/utils.py:245`, `packages/pymodaq_gui/src/pymodaq_gui/parameter/ioxml.py:377`, `packages/pymodaq_gui/src/pymodaq_gui/h5modules/browsing.py:442`, `packages/pymodaq_gui/src/pymodaq_gui/plotting/data_viewers/viewer1Dbasic.py:102,172`, `packages/pymodaq_gui/src/pymodaq_gui/plotting/data_viewers/viewer.py:296`
- notes: default None, build in body; keep names, keywords and positions. Confirmed bugs: h5tree_to_QTree shared pixmap_items (browsing.py:494 omits it, utils.py:298 appends); walk_xml_to_parameter shared params when the caller omits it (docstring example :398; in-repo callers pass params=[]). viewer1Dbasic.py:102 needs labels=[] in body (lines 105-106 slice/compare). 172 and browsing.py:442 are read-only cleanup. Add regression tests that fail on current code (call twice with the default); edit no existing test. Leave roi.py out (#1515).
- verdicts: decider-compat-risk: approve — names/keywords/positions unchanged, no hard rule touched; decider-test-change: approve — tests only added, must fail before the fix
- status: approved — owner, 2026-11-26

## T-pymodaq_gui-002 Drop the direct PyQt6 import in PatternCompleter
- scope: pymodaq_gui   specialty: hygiene
- risk: low
- files: `packages/pymodaq_gui/src/pymodaq_gui/utils/widgets/pattern_completer.py:188`
- notes: delete the local `from PyQt6.QtWidgets import QListView` (qtpy QListView already imported at line 8). Under PySide6 word_wrap raises ImportError or is silently ignored. Add a test in tests/utils/widgets/pattern_completer_test.py asserting popup.wordWrap(), run under PyQt6 and PySide6 (PYTEST_QT_API, offscreen).
- verdicts: decider-compat-risk: approve — hard rule 6 fix, no public name changes; decider-test-change: approve — test added, none weakened
- status: approved — owner, 2026-11-26

## T-pymodaq_gui-003 Manager sub-entry status colours via StatusPalette
- scope: pymodaq_gui   specialty: uiux
- risk: medium
- files: `packages/pymodaq_gui/src/pymodaq_gui/managers/manager_base.py:58-94`
- notes: None->OFF, True->IDLE, False->ERROR (utils/status_palette.py:121-128; ERROR is orange, not darkRed). Keep set_status(int, bool) signature and the .colors attribute (note in PR if its element type changes). DecorationRole icons (:80-85) and settings_manager.py:288 out of scope. Before/after screenshots, light and dark.
- verdicts: decider-compat-risk: approve (medium) — public set_status/.colors kept, visible colour change unrendered; decider-triage (2nd): approve — mapping exists, .colors never read in repo
- status: approved — owner, 2026-11-26

## T-pymodaq_gui-004 Exclude generated icon resources from jscpd
- scope: tool   specialty: tool
- risk: low
- files: `.agents/scripts/scan.py:126`
- notes: add `--ignore "**/resources/material_icons/resources/**"` to the jscpd call (no jscpd config file exists); state the ignore pattern in the jscpd section header of the scan. Branch agent-tool/<name>, no product files. Scan sha256 of all scopes changes afterwards (expected).
- verdicts: decider-compat-risk: approve — scanner only, files are rcc-generated (hard rule 3); decider-triage (2nd): approve — 24% duplication is all generated
- status: approved — owner, 2026-11-26 (tool path now exists)

## T-pymodaq_gui-005 Remove unused and duplicate imports
- scope: pymodaq_gui   specialty: hygiene
- risk: low
- files: `packages/pymodaq_gui/src/pymodaq_gui/parameter/pymodaq_ptypes/pixmap.py:5-7`, `packages/pymodaq_gui/src/pymodaq_gui/managers/settings/subentries.py:15`, `packages/pymodaq_gui/src/pymodaq_gui/plotting/items/roi.py:17`, `packages/pymodaq_gui/src/pymodaq_gui/plotting/utils/filter.py:20`, `packages/pymodaq_gui/src/pymodaq_gui/parameter/pymodaq_ptypes/tableview.py:5`, `packages/pymodaq_gui/src/pymodaq_gui/plotting/data_viewers/viewer0D.py:2`
- notes: roi.py: drop only `ROI` from the pyqtgraph import at line 17 (shadowed by class ROI at 221); drop roi.py if #1515 touches line 17. Do not touch pymodaq_ptypes/__init__.py, __init__ re-exports, viewerND.py, ioxml.py.
- verdicts: decider-compat-risk: approve — every name stays importable, no re-export lost; decider-triage (2nd): approve — each import checked duplicate/unused
- status: done — PR #29 open, awaiting the human: touches a UI scope: packages/pymodaq_gui/src/pymodaq_gui/managers/settings/subentries.py, packages/pymodaq_gui/src/pymodaq_gui/parameter/pymodaq_ptypes/pixmap.p
