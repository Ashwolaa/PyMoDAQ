# Consortium status — generated 2026-11-22 21:19 by `scripts/status.py`

Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.

## Now
- `dev_agent` at `5d2be0977`; 155 commits ahead of upstream/dev (34 files changed, 356 insertions(+), 82 deletions(-))
- today: runs 9/20, specialist_runs 6/10, prs_opened 3/6, reviews 3/10; outcomes: ok 8, failed 1
- last /usage reading: 2026-11-22T20:19:54.165000+00:00  session 54% (resets Nov 22, 11:40pm (Europe/Paris))  week 5% (resets Nov 29, 12am (Europe/Paris))
- next cycle step: `merge`

## Needs you
- **T-pymodaq_utils-M11** — done — PR #17 open, awaiting the human: registry risk is medium; plan risk is medium; a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; touches tests: packages/p
- **T-pymodaq_utils-006** — done — PR #18 open, awaiting the human: touches tests: packages/pymodaq_utils/tests/config_test.py
- **T-pymodaq_data-001** — done — PR #16 open, awaiting the human: a decider vetoed or blocked it in the plan
- blocked: **T-pymodaq_utils-M06** — blocked — pymodaq test scope hangs (extension_loading_test::test_load[Scanner]) on both Qt backends and on the base commit, so qt-backend checks cannot be recorded; code and utils tests are fine

## In flight
- `agent/pymodaq_utils/refactor/2026-11-22-set-logger-must` (T-pymodaq_utils-007, risk medium): pushed, waiting for /optimize-merge
- T-pymodaq_utils-008 Isolate test_nested_update_from_user — approved — owner, 2026-11-22
- T-pymodaq_utils-011 packages.get_entrypoints delegates to utils.get_entrypoints — approved — owner, 2026-11-22
- T-pymodaq_utils-M12 Drift test for the duplicated entry-point group lists — approved — owner, 2026-11-22

## Open findings (go to the next /optimize-plan of their scope)
- [pymodaq] CI tests-pymodaq.yml tests (ubuntu-latest, pyside6): crash (Fatal Python error: Segmentation), also on upstream/dev
- [pymodaq_utils] Config files freeze the template on first start and only gain missing keys: type changes and renames survive branch switches until the file is deleted
- [pymodaq_data] numpy_func.py:47 returns NotImplementedError instead of raising/returning NotImplemented
- [pymodaq_data] Unverified ruff bug-risk items: B007 loop vars, B018 data.py:1718, F811 append data.py:4226/4241, backends.py:345 unreachable, hyperspy.py:57 data_arr
- [pymodaq_data] numpy_func.py:47 returns NotImplementedError instead of raising it
- [pymodaq_data] data.py:4225 and :4240 redefine append (F811)
- [pymodaq_data] exporters/hyperspy.py:57 assigns data_array, never used (F841)
- [pymodaq] packages/pymodaq tests hang at extension_loading_test.py::TestExtensions::test_load[Scanner] (offscreen, pyqt6 and pyside6, also on base)
- [pymodaq_utils] config_test::test_nested_update_from_user fails (both backends, also on base)
- [pymodaq_utils] logger.py: import sys unused after T-007; __init__.py ConfigError handler untested

## Recent runs
| run | command | outcome | min | out tok | note |
|---|---|---|---|---|---|
| 2026-11-20-merge-T-pymodaq_utils-010-r1 | optimize-merge | ok | 5.7 | 5669 | T-pymodaq_utils-010: done — PR #15 merged (auto: low risk, approved by |
| plan-pymodaq_data-20261122 | optimize-plan | ok | 3.5 | 53355 |  |
| 2026-11-22-run-T-pymodaq_data-001 | optimize-run | ok | 2.7 | 9458 | imports + exception hygiene, 12 files, 85 lines |
| 2026-11-22-merge-T-pymodaq_data-001-r1 | optimize-merge | ok | 7.0 | 10756 | T-pymodaq_data-001: done — PR #16 open, awaiting the human: a decider  |
| 2026-11-22-run-T-pymodaq_utils-M06 | optimize-run | failed | 71.2 | 10592 | pymodaq test scope hangs (extension_loading_test::test_load[Scanner])  |
| 2026-11-22-run-T-pymodaq_utils-M11 | optimize-run | ok | 1.8 | 7607 | shared ft/ift/ft2/ift2 input checks, pinning tests first; pre-existing |
| 2026-11-22-merge-T-pymodaq_utils-M11-r1 | optimize-merge | ok | 5.6 | 5539 | T-pymodaq_utils-M11: done — PR #17 open, awaiting the human: registry  |
| 2026-11-22-run-T-pymodaq_utils-006 | optimize-run | ok | 2.2 | 7142 | dead plural fallbacks deleted; characterisation tests added; pre-exist |
| 2026-11-22-merge-T-pymodaq_utils-006-r1 | optimize-merge | ok | 5.4 | 6539 | T-pymodaq_utils-006: done — PR #18 open, awaiting the human: touches t |
| 2026-11-22-run-T-pymodaq_utils-007 | optimize-run | ok | 1.9 | 7756 | set_logger raises ConfigError; test added; coverage logger.py 51->53%; |

## Done so far
- tasks done: 20; PRs merged into dev_agent: 13
