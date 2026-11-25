# Handoff: pymodaq_scripting — 2026-11-25

## Done
- T-pymodaq_scripting-001 (hygiene): __all__ in __init__.py, unused imports dropped in examples/dashboard_script.py, redundant .keys() dropped in utils.py. Branch agent/pymodaq_scripting/hygiene/2026-11-25 (commit 2b1255e80), pushed, no PR yet.

## Open findings (ranked)
1. docs/src/user_folder/common_questions.rst:47 uses old pymodaq.scripting import [risk: low] (may join T-002)

## Blocked
- none

## Next step
`/optimize-merge T-pymodaq_scripting-001` (pr-reviewer, then PR). Then run T-pymodaq_scripting-002 (docs).

## Evidence
- tests: flake8 blocking 0; layering 3 passed; pyqt6 1 passed; pyside6 1 passed
- merge_gate lint OK, 8 changed lines
- coverage diff: n/a
- screenshots: n/a
