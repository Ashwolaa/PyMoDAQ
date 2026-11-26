verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_gui-005 r1 (branch agent/pymodaq_gui/hygiene/2026-11-26, commit 9666e3113)

## Task match and drift
- Diff touches exactly the 6 files/lines listed in the plan entry; 10 removed/changed lines, no reformatting, no other edits.
- `merge_gate.py lint`: LINT OK (10 changed lines, product files only, trailers present).
- Excluded files (pymodaq_ptypes/__init__.py, viewerND.py, ioxml.py, __init__ re-exports) untouched: verified in `git diff --name-only`.
- roi.py condition ("drop if #1515 touches line 17"): local branch fix/viewernd-roi-select-signal (PR #1515) has no diff on roi.py vs upstream/dev. Upstream PR itself not queried (gh on upstream blocked by hook).

## Correctness (each removal verified on the branch)
- packages/pymodaq_gui/src/pymodaq_gui/managers/settings/subentries.py:15 - duplicate `StrEnum` import; line 9 still imports it, used at :29.
- packages/pymodaq_gui/src/pymodaq_gui/parameter/pymodaq_ptypes/pixmap.py:5-7 - exact duplicates of lines 2-4 (subset); WidgetParameterItem/SimpleParameter still imported at :4.
- packages/pymodaq_gui/src/pymodaq_gui/parameter/pymodaq_ptypes/tableview.py:5 - `ColorButton` has no use left in the file.
- packages/pymodaq_gui/src/pymodaq_gui/plotting/data_viewers/viewer0D.py:2 - `Real` has no use left in the file.
- packages/pymodaq_gui/src/pymodaq_gui/plotting/items/roi.py:17 - pyqtgraph `ROI` was shadowed by `class ROI` at :221; no code reference to `ROI` between :17 and :221 (docstrings only); `pgROI` alias kept.
- packages/pymodaq_gui/src/pymodaq_gui/plotting/utils/filter.py:20 - duplicate of `ROIViewerManager` import at :3, still used in annotations (:241, :258, :324).
- flake8 F821/F811 on all 6 branch files: no undefined name, no remaining redefinition.

## Behaviour and API
- No module defines `__all__`; grep across packages/ finds no import of StrEnum, ColorButton, Real, ROIViewerManager, or pyqtgraph ROI through these modules, and no `import *` of them. `roi.ROI` still resolves to the local class (as before, since it shadowed the import). public_api: no.

## Tests
- Hygiene task, no bug fix: fails_without_fix n/a. Caller reports pytest pymodaq_gui under pyqt6 and pyside6 with only 2 pre-existing errors (not re-run here).

## Docs
- No docs or docstrings changed. Commit message claims match the diff.

outside: packages/pymodaq_gui/src/pymodaq_gui/plotting/items/roi.py|remaining-unused-imports | The 6 touched files still have other unused imports (e.g. roi.py LinearRegionItem, Slot; pixmap.py QByteArray, QObject; filter.py QtCore, roi_format), found by flake8 F401, re-export use not checked

summary: Removes 6 duplicate or unused imports in pymodaq_gui (pixmap, subentries, tableview, viewer0D, roi, filter); no public name or behaviour changes.
