# Consortium status — generated 2026-11-22 19:26 by `scripts/status.py`

Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.

## Now
- `dev_agent` at `544bf9a6f`; 130 commits ahead of upstream/dev (22 files changed, 324 insertions(+), 29 deletions(-))
- today: runs 2/20, specialist_runs 1/10, prs_opened 0/6, reviews 0/10; outcomes: ok 2
- last /usage reading: 2026-11-22T18:22:35.228000+00:00  session 25% (resets Nov 22, 11:40pm (Europe/Paris))  week 3% (resets Nov 29, 12am (Europe/Paris))
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
- `agent/pymodaq_data/hygiene/2026-11-22` (T-pymodaq_data-001, risk low): pushed, waiting for /optimize-merge

## Open findings (go to the next /optimize-plan of their scope)
- [pymodaq] CI tests-pymodaq.yml tests (ubuntu-latest, pyside6): crash (Fatal Python error: Segmentation), also on upstream/dev
- [pymodaq_utils] Config files freeze the template on first start and only gain missing keys: type changes and renames survive branch switches until the file is deleted
- [pymodaq_data] numpy_func.py:47 returns NotImplementedError instead of raising/returning NotImplemented
- [pymodaq_data] Unverified ruff bug-risk items: B007 loop vars, B018 data.py:1718, F811 append data.py:4226/4241, backends.py:345 unreachable, hyperspy.py:57 data_arr
- [pymodaq_data] numpy_func.py:47 returns NotImplementedError instead of raising it
- [pymodaq_data] data.py:4225 and :4240 redefine append (F811)
- [pymodaq_data] exporters/hyperspy.py:57 assigns data_array, never used (F841)

## Recent runs
| run | command | outcome | min | out tok | note |
|---|---|---|---|---|---|
| plan-pymodaq_utils-r2-20261119 | optimize-plan | ok | 6.5 | 81538 |  |
| plan-pymodaq_utils-r3-20261119 | optimize-plan | ok |  | 409 |  |
| 2026-11-19-run-T-pymodaq_utils-009 | optimize-run | ok | 6.2 | 8680 | docstrings for six public names; _literal_value checked unchanged; pre |
| 2026-11-19-merge-T-pymodaq_utils-009 | optimize-merge | budget | 0.2 | 1279 | STOP reviews 14>=14; merged 0, awaiting human 0, blocked 0 (T-009 unto |
| 2026-11-19-run-T-pymodaq_utils-010 | optimize-run | budget | 0.3 | 1415 | DISABLE: day over budget; T-010 not started |
| 2026-11-20-merge-T-pymodaq_utils-009-r1 | optimize-merge | ok | 6.0 | 6401 | T-pymodaq_utils-009: done — PR #14 merged (auto: low risk, approved by |
| 2026-11-20-run-T-pymodaq_utils-010 | optimize-run | ok | 0.6 | 3748 | docs: 3 check_plugin codes added |
| 2026-11-20-merge-T-pymodaq_utils-010-r1 | optimize-merge | ok | 5.7 | 5669 | T-pymodaq_utils-010: done — PR #15 merged (auto: low risk, approved by |
| plan-pymodaq_data-20261122 | optimize-plan | ok | 3.5 | 53355 |  |
| 2026-11-22-run-T-pymodaq_data-001 | optimize-run | ok | 2.7 | 9458 | imports + exception hygiene, 12 files, 85 lines |

## Done so far
- tasks done: 17; PRs merged into dev_agent: 12
