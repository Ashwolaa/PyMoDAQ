# Handoff: pymodaq_utils — 2026-11-22 (/optimize-run T-pymodaq_utils-M11)

## Done
- T-M11 on agent/pymodaq_utils/refactor/2026-11-22-shared-input-checks (pushed, no PR yet):
  972735a78 pinning tests (exact exceptions, defaults ift=0 / ft=-1), b3ff494b0 private helpers
  _check_ft_input / _check_ft2_input shared by ft/ift and ft2/ift2. Behaviour unchanged.
- Checks: flake8, layering, merge_gate lint OK; pyqt6 and pyside6: 329 passed, 1 pre-existing fail.

## Blocked
- T-M06 still blocked (pymodaq extension_loading_test Scanner hang, unchanged).

## Open findings
1. pymodaq extension_loading_test Scanner load hangs offscreen [medium]
2. config_test::test_nested_update_from_user fails on base too [low]

## Next step
`/optimize-merge T-pymodaq_utils-M11`; then M12 (test only, pymodaq scope).

## Evidence
- task.py checks: pyqt6/pyside6 pymodaq_utils 1 failed (pre-existing), 329 passed
