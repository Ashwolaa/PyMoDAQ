# Consortium status — generated 2026-11-22 22:21 by `scripts/status.py`

Do not edit: regenerate with `python3 .agents/scripts/status.py --write`. Design: `.agents/BRIEFING.md`.

## Now
- `dev_agent` at `e1c39aa6c`; 174 commits ahead of upstream/dev (36 files changed, 474 insertions(+), 134 deletions(-))
- today: runs 13/20, specialist_runs 8/10, prs_opened 4/6, reviews 5/10; outcomes: ok 12, failed 1
- last /usage reading: 2026-11-22T21:18:39.958000+00:00  session 67% (resets Nov 22, 11:40pm (Europe/Paris))  week 6% (resets Nov 29, 12am (Europe/Paris))
- next cycle step: `merge`

## Needs you
- grill pending: **config-isolation** (pymodaq_utils) — answer with `/optimize-grill config-isolation`
- **T-pymodaq_utils-M11** — done — PR #17 open, awaiting the human: registry risk is medium; plan risk is medium; a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; touches tests: packages/p
- **T-pymodaq_utils-006** — done — PR #18 open, awaiting the human: touches tests: packages/pymodaq_utils/tests/config_test.py
- **T-pymodaq_utils-008** — done — PR #19 open, awaiting the human: a decider vetoed or blocked it in the plan; plan shows 1 approving decider(s), 2 needed; touches tests: packages/pymodaq_utils/tests/config_test.py
- **T-pymodaq_data-001** — done — PR #16 open, awaiting the human: a decider vetoed or blocked it in the plan
- blocked: **T-pymodaq_utils-M06** — blocked — pymodaq test scope hangs (extension_loading_test::test_load[Scanner]) on both Qt backends and on the base commit, so qt-backend checks cannot be recorded; code and utils tests are fine
- blocked: **T-pymodaq_utils-007** — blocked — review: set_logger now raises ConfigError instead of calling sys.exit on a non-list debug_level, and the package import prints its message; the test must use a real con

## In flight
- `agent/pymodaq_utils/refactor/2026-11-22-packages-get-entrypoints` (T-pymodaq_utils-011, risk medium): pushed, waiting for /optimize-merge
- T-pymodaq_utils-007 set_logger must not kill the importing process — blocked — review: set_logger now raises ConfigError instead of calling sys.exit on a non-list debug_level, and the package import prints its message; the test must use a real con
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
- [pymodaq_utils] the new `except ConfigError` branch in the package import has no test
- [pymodaq_utils] error message calls config(...) a second time instead of reusing log_level (pre-existing)
- [pymodaq_utils] test_load_system_config writes into the real ~/.pymodaq config folders and mutates global TOML_DICT (already flagged out of scope by the plan; leak no

## Recent runs
| run | command | outcome | min | out tok | note |
|---|---|---|---|---|---|
| 2026-11-22-run-T-pymodaq_utils-M06 | optimize-run | failed | 71.2 | 10592 | pymodaq test scope hangs (extension_loading_test::test_load[Scanner])  |
| 2026-11-22-run-T-pymodaq_utils-M11 | optimize-run | ok | 1.8 | 7607 | shared ft/ift/ft2/ift2 input checks, pinning tests first; pre-existing |
| 2026-11-22-merge-T-pymodaq_utils-M11-r1 | optimize-merge | ok | 5.6 | 5539 | T-pymodaq_utils-M11: done — PR #17 open, awaiting the human: registry  |
| 2026-11-22-run-T-pymodaq_utils-006 | optimize-run | ok | 2.2 | 7142 | dead plural fallbacks deleted; characterisation tests added; pre-exist |
| 2026-11-22-merge-T-pymodaq_utils-006-r1 | optimize-merge | ok | 5.4 | 6539 | T-pymodaq_utils-006: done — PR #18 open, awaiting the human: touches t |
| 2026-11-22-run-T-pymodaq_utils-007 | optimize-run | ok | 1.9 | 7756 | set_logger raises ConfigError; test added; coverage logger.py 51->53%; |
| 2026-11-22-merge-T-pymodaq_utils-007-r1 | optimize-merge | ok | 2.2 | 8063 | T-pymodaq_utils-007: blocked — review: set_logger now raises ConfigErr |
| 2026-11-22-run-T-pymodaq_utils-008 | optimize-run | ok | 1.5 | 6449 | test isolated via get_set_local_dir patch; coverage unchanged |
| 2026-11-22-merge-T-pymodaq_utils-008-r1 | optimize-merge | ok | 6.1 | 6297 | T-pymodaq_utils-008: done — PR #19 open, awaiting the human: a decider |
| 2026-11-22-run-T-pymodaq_utils-011 | optimize-run | ok | 1.9 | 6233 | packages.get_entrypoints delegates to utils (list; deprecation_msg); o |

## Done so far
- tasks done: 21; PRs merged into dev_agent: 15
