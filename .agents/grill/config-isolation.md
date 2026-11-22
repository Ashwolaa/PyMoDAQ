# Grill: config-isolation

## Decision
Tests run against the real `~/.pymodaq` (`get_set_local_dir(user=True)` is `Path.home()/'.pymodaq'`, cached, no env override), and the config singleton saves its modified values at exit. Two leaks already seen: `test_save_current_defaults_to_dated_folder...` (PR #1534) and the import-time `config_viewer['viewer_in_thread'] = True` in `daq_viewer_test.py:34`. The first one made `test_load[Scanner]` hang and blocked T-pymodaq_utils-M06. Which isolation do we build changes how every test and every agent run behaves.

## Questions
1. Where does isolation live: a root/session `conftest.py` that points HOME at a temporary directory before `pymodaq_utils.config` is imported, or an override inside the library (e.g. a `PYMODAQ_CONFIG_DIR` environment variable honoured by `get_set_local_dir`)?
   Recommended: the environment variable. It also helps users and the agents' scripts, and the conftest then only sets it; patching `Path.home()` fails because `get_set_local_dir` is cached.
2. Should `Config.save` refuse to write into the real user folder while running under pytest?
   Recommended: yes, as a second layer, one small check on `PYTEST_CURRENT_TEST`; skip it if question 1 is done first and the suite is clean.
3. Is this a PR to upstream (library change plus conftest), or fork-only for the agents first?
   Recommended: fork-only first (agents' suite and `[tools].env`), upstream PR after one clean week of runs.
4. `h5manager.create_new_file` shows a modal `QMessageBox` when the saver cannot be created, which hangs a headless run. Change it (log and fall back to the default folder) or leave it?
   Recommended: leave it for now; it is user-facing UI behaviour and should be a separate decision.
5. Do the agents' tests run in the shared `~/.pymodaq` today by design (R5 explores isolation)? Is a throwaway HOME per agent run acceptable, given the cost of re-creating the config on every run?
   Recommended: yes, a throwaway HOME per run; the config is cheap to recreate and it removes the drift between branches.
