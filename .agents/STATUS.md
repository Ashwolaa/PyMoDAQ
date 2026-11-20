# Consortium status — generated 2026-11-20 07:33 by `scripts/status.py`

Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.

## Now
- `dev_agent` at `46a104cb7`; 113 commits ahead of upstream/dev (21 files changed, 321 insertions(+), 29 deletions(-))
- today: runs 2/20, specialist_runs 1/10, prs_opened 1/6, reviews 1/10; outcomes: ok 2
- last /usage reading: 2026-11-20T06:33:49.972000+00:00  session 22% (resets Nov 20, 12pm (Europe/Paris))  week 87% (resets Nov 22, 12am (Europe/Paris))
- next cycle step: `merge`

## Needs you
- approve or drop **T-pymodaq_utils-M06** Moved plugin_tools shims never call deprecation_msg — proposed (public API, touches tests, leaves the scope) (`.agents/plans/2026-11-19-pymodaq_utils-merged.md`)
- approve or drop **T-pymodaq_utils-M11** Shared input checks for ft/ift/ft2/ift2 — proposed (touches tests) (`.agents/plans/2026-11-19-pymodaq_utils-merged.md`)
- approve or drop **T-pymodaq_utils-M12** Drift test for the duplicated entry-point group lists — proposed (tests, outside the pymodaq_utils scope) (`.agents/plans/2026-11-19-pymodaq_utils-merged.md`)
- approve or drop **T-pymodaq_utils-006** Delete the dead plural fallbacks in Config.__call__ (absorbs the Config.__call__ part of T-003) — proposed (adds a test; public accessor) (`.agents/plans/2026-11-19-pymodaq_utils-r2.md`)
- approve or drop **T-pymodaq_utils-007** set_logger must not kill the importing process — proposed (touches tests, public set_logger) (`.agents/plans/2026-11-19-pymodaq_utils-r2.md`)
- approve or drop **T-pymodaq_utils-008** Isolate test_nested_update_from_user — proposed (touches tests) (`.agents/plans/2026-11-19-pymodaq_utils-r2.md`)
- approve or drop **T-pymodaq_utils-011** packages.get_entrypoints delegates to utils.get_entrypoints — proposed (public API) (`.agents/plans/2026-11-19-pymodaq_utils-r2.md`)

## In flight
- `agent/docs/docs/2026-11-20` (T-pymodaq_utils-010, risk low): pushed, waiting for /optimize-merge

## Open findings (go to the next /optimize-plan of their scope)
- [pymodaq] CI tests-pymodaq.yml tests (ubuntu-latest, pyside6): crash (Fatal Python error: Segmentation), also on upstream/dev

## Recent runs
| run | command | outcome | min | out tok | note |
|---|---|---|---|---|---|
| 2026-11-19-merge-T-pymodaq_utils-M07 | optimize-merge | ok | 6.4 | 10514 | merged 1, awaiting human 0, blocked 0 |
| 2026-11-19-run-T-pymodaq_utils-M08 | optimize-run | ok | 4.9 | 4245 | M08 rework after review r1, CI green |
| 2026-11-19-merge-T-pymodaq_utils-M08 | optimize-merge | ok | 6.1 | 7742 | merged 1, awaiting human 0, blocked 0 |
| plan-pymodaq_utils-r2-20261119 | optimize-plan | ok | 6.5 | 81538 |  |
| plan-pymodaq_utils-r3-20261119 | optimize-plan | ok |  | 409 |  |
| 2026-11-19-run-T-pymodaq_utils-009 | optimize-run | ok | 6.2 | 8680 | docstrings for six public names; _literal_value checked unchanged; pre |
| 2026-11-19-merge-T-pymodaq_utils-009 | optimize-merge | budget | 0.2 | 1279 | STOP reviews 14>=14; merged 0, awaiting human 0, blocked 0 (T-009 unto |
| 2026-11-19-run-T-pymodaq_utils-010 | optimize-run | budget | 0.3 | 1415 | DISABLE: day over budget; T-010 not started |
| 2026-11-20-merge-T-pymodaq_utils-009-r1 | optimize-merge | ok | 6.0 | 6401 | T-pymodaq_utils-009: done — PR #14 merged (auto: low risk, approved by |
| 2026-11-20-run-T-pymodaq_utils-010 | optimize-run | ok | 0.6 | 3748 | docs: 3 check_plugin codes added |

## Done so far
- tasks done: 16; PRs merged into dev_agent: 11
