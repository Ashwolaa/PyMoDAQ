# Handoff: pymodaq_utils — 2026-11-22 (/optimize-merge)

## Done
- PR #16 (agent/pymodaq_data/hygiene/2026-11-22) merged into dev_agent (seen by sync).
- T-M11 (shared ft/ift input checks): pr-reviewer approve, PR #17 open, CI green
  (compile-doc, tests-utils, typing); pyqt6/pyside6 pymodaq_utils 329 passed, 1 pre-existing fail.

## Blocked
- T-M06 still blocked (pymodaq extension_loading_test Scanner hang, unchanged).

## Open findings
1. pymodaq extension_loading_test Scanner load hangs offscreen [medium]
2. config_test::test_nested_update_from_user fails on base too [low]

## Next step
Human: decide PR #17 (not auto-merged: registry and plan risk medium, a decider vetoed or blocked it in the plan,
1 of 2 needed approving deciders, touches tests/math_utils_test.py). Then M12 (test only, pymodaq scope).

## Evidence
- Review: .agents/reports/pymodaq_utils/2026-11-22-pr-review-T-pymodaq_utils-M11-r1.md
