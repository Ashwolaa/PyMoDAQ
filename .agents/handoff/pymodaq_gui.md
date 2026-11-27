# Handoff: pymodaq_gui — 2026-11-28 /optimize-merge (max 40 lines, overwrite each run)

## Done
- T-pymodaq_gui-004 (run 2026-11-28-merge-T-pymodaq_gui-004-r1): PR #33 merged into dev_agent (auto:
  low risk, decider-compat-risk + decider-triage + pr-reviewer approve, 30 lines, tool code only).
  scan.py now passes `--ignore "**/resources/material_icons/resources/**"` to jscpd; reviewer measured
  pymodaq_gui duplication 24.22% -> 1.72% (917 generated-icon clones gone).
- Rebased on dev_agent before review; local checks green (layering, lint, agents tests 55 passed).

## Awaiting the human
- PR #32 (T-003): risk medium, public_api yes (`.colors` GlobalColor -> QColor); add the screenshots in
  .agents/reports/pymodaq_gui/screenshots/T-pymodaq_gui-003/{before,after}_{light,dark}.png to its body.
- PR #31 (T-002), PR #30 (T-001), PR #29 (T-005, touches a UI scope): still open.

## Open findings (ranked)
1. test-icon-qt-preexisting-fail: action_manager_test.py::test_icon_qt fails on base and branch.
2. flake8-syntaxwarning-escape-457: invalid escape '\*' at <unknown>:457 (file unidentified).
3. remaining-unused-imports (review, T-005 files).
- editor_test / editor_cache_test collection errors (QtWebEngine) are pre-existing.

## Blocked
- none.

## Queue
- Plan 2026-11-26-pymodaq_gui: no approved task left; no merge candidate left.
- Expected: scan sha256 of every scope changes on the next scan (jscpd ignore).

## Next step
- Human: review PR #32 (attach screenshots), then #31, #30, #29.
- Agents: re-scan pymodaq_gui (`/optimize-plan pymodaq_gui`) once the open PRs are settled.

## Evidence
- PR #33, merge commit a228e575b; review .agents/reports/pymodaq_gui/2026-11-28-pr-review-T-pymodaq_gui-004-r1.md
