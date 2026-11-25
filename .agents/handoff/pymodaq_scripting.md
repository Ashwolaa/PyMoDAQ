# Handoff: pymodaq_scripting — 2026-11-25

## Done
- T-pymodaq_scripting-001 (hygiene): PR #27 merged into dev_agent (auto-merge: low risk, 8 lines, reviewer approve, CI green).
  __all__ in __init__.py, unused imports dropped in examples/dashboard_script.py, redundant .keys() dropped in utils.py.

## Open findings (ranked)
1. docs/src/user_folder/common_questions.rst:47 uses old pymodaq.scripting import [risk: low] (may join T-002)
2. Only API effect of T-001: `from pymodaq_scripting import *` no longer exports submodule names devices/utils; external star-import use unverified.

## Blocked
- none

## Next step
`/optimize-run T-pymodaq_scripting-002` (docs), then `/optimize-merge T-pymodaq_scripting-002`.

## Evidence
- reviewer: approve (report .agents/reports/pymodaq_scripting/2026-11-25-pr-review-T-pymodaq_scripting-001-r1.md)
- checks after rebase: flake8 blocking 0; layering 3 passed; pyqt6 1 passed; pyside6 1 passed
- PR CI green (compile-doc, tests-scripting, typing)
