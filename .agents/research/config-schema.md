# config-schema: surviving schema changes and branch switches
Run 2026-11-23, prototype `agent-rd/config-schema` (commit 272b75d0e, worktree /tmp/rd-config-schema). Direction: `.agents/grill/config-isolation.md`.

## Current behaviour (packages/pymodaq_utils/src/pymodaq_utils/config.py, re-verified)
- `get_set_path` :109-122 falls back to `Path.home()/.pymodaq` when `/etc/.pymodaq` cannot be created: system and user file are then ONE file (seen: WARNING at every import here).
- `get_set_local_dir` :125 `@functools.cache`, `Path.home()` only, no override.
- `load` :414-441: no system file -> whole template copied (:433); else `check_config` :203-225 only adds missing keys; user file deep-merged over it (:284). `save` :443 writes `_modified_config` at exit (atexit :329).
- Configs: 4 templates (utils, data, gui, pymodaq `utils/config.py:64`), `config_template_path = None` for data_mixer, optimizers_base, scan_config; plugins subclass `BaseConfig` (test in pymodaq/tests/utils/plugin_configs_test.py).

## Real schema changes in git history (test cases)
- scalar -> list: `hdf5_backend` -> `backend` list (c295ada7d 2026-02-08, 4f0982276 02-21); `debug_level`, `dynamic` -> list + `debug_levels` (81c1fbf84 2025-12-01); `controls_dock_layout` 'vertical' -> ['vertical','horizontal'] (9ad68c435 2026-10-06).
- default changed: dock layouts horizontal -> vertical (753c4f84d, 87a70ae00); `default_preset_for_*` values; `swmr_enabled` true/false flips.
- moved between files: style, qtbackend, data_saving, plotting left pymodaq's template for gui/data (c295ada7d); `control_module_ini_polling` (ff6cd60d3), `rois_as_popup`/`roi_as_popup` (704b756e3).
- removed: `viewer_in_thread`, `scan_in_thread` (1cfaeb646), `[network.tcp-server]`, `[manager] ask_before_executing_unsaved`, `[presets]`.
- Consequence seen today: `pymodaq/tests/utils/config_test.py::test_required_config_entries` asserts the removed `viewer_in_thread`; it passes only thanks to a leaked value in the owner's ~/.pymodaq and FAILS with a fresh HOME on dev_agent (verified, pre-existing).

## Comparison
| approach | gains | what breaks |
|---|---|---|
| (a) sparse user file only | defaults always new | system file stops being a full, editable list (docs/admins rely on it); old users already hold full files; plugins reading the file directly |
| (b) schema version + migrations | handles renames/moves (the only case no type check can see) | needs author discipline; plugins without version: stay at 0, nothing runs (safe) |
| (c) type check, back up, reset | automatic for retyping, no author work | cannot know a rename; reset loses a user value (backup kept) |
| (d) PYMODAQ_CONFIG_DIR | tests/agents/devs isolated per branch | none if unset; new var to document |
None alone suffices. Frozen defaults (the template copied once) need a fifth piece: remember the template that last wrote the file (snapshot) and take the new default where the file still equals the old one (three-way merge).

## Prototype (b)+(c)+snapshot+(d), all in config.py, no template edit
- `reconcile_config(template, config, previous, add_missing)`: adds keys; scalar -> [scalar]; list -> first element (project convention); int accepted for float; other mismatch reset; unknown keys never deleted; value == previous default and template changed -> new default.
- `BaseConfig.config_schema_version` (default 0) + `config_migrations={v: fn(dict)}`, helper `rename_key`; versions stored with the template snapshot in `config/.template_snapshots/<name>.toml`.
- Any destructive change: `<file>.<stamp>.bak` copy + one warning listing the keys.
- `PYMODAQ_CONFIG_DIR`: `<dir>/system`, `<dir>/user` (distinct, no collapse to one file), read at each call (inner cache keyed on the value, `cache_clear` kept). `Config.save` refuses the real `~/.pymodaq` under pytest when the variable is unset. Root `conftest.py` sets a temp dir.
- Tests `packages/pymodaq_utils/tests/config_schema_test.py` (6): branch switch (old file, new template: retype + rename, other values kept, backup left), new default reaches untouched key (own value kept), no deletion, list -> scalar, two dirs isolated. Pass; utils 341, data 655 pass in scratch HOME; layering test, gui config tests, flake8 clean. pymodaq tests/utils/config_test: 1 failure = the pre-existing one above.
- Found: running `pytest` from `packages/X` DID load the repo-root conftest here (HOME stayed empty; with `--noconftest` it filled). Unverified for the CI invocation and for pytest-xdist workers (env is inherited, so likely fine).

## Plugin compatibility (hard rule 1)
Nothing removed or renamed. `get_set_local_dir` keeps its signature and `.cache_clear`. New class attributes have defaults; plugins with a template and no version behave as before plus type reconcile (new behaviour: a plugin value of another type than its template is reset with a backup; plugin authors using scalar where the template has a list get a list). Snapshot dir sits inside `config/`; code listing `config/*.toml` is unaffected (dotted subfolder). `Config.__call__` plural/singular fallbacks (T-pymodaq_utils-006) can stay; with scalar -> list migration they become redundant, remove only after a deprecation cycle. System/user split under the env var differs from the home fallback layout (unverified effect on plugins that build paths from `get_set_local_dir()` and assume `.pymodaq` name).

## Does HOME=scratch isolate the agents' tests? Yes on Linux (verified)
`~/.pymodaq` listing (path, mtime, size, 160 entries) before and after running pymodaq_utils (335 passed) and pymodaq_data (655 passed) on unmodified dev_agent code with `HOME=/tmp/scratch_home4`: identical; the scratch HOME received 11 files. Not verified: Windows (`Path.home()` reads USERPROFILE, so set both), the pymodaq/gui suites, and a GUI test touching `/etc` (falls back to HOME anyway).
Incident: my first `python -c "import pymodaq_utils"` (before I set HOME) loaded the real config (atexit save); `~/.pymodaq/config` mtimes 20:59-21:01 may be mine or concurrent runs; contents unverified. All later runs used scratch HOME.

## Proposed tasks for /optimize-plan (all `proposed`: public API)
1. pymodaq_utils: `PYMODAQ_CONFIG_DIR` in `get_set_local_dir` + `Config.save` pytest guard + conftests (also in packages/pymodaq, gui, data tests). Fork-only a week, per grill answer.
2. pymodaq_utils: `reconcile_config`, backup and snapshot in `BaseConfig.load` (docs: how plugins version a template).
3. Tests: fix `test_required_config_entries` (stale `viewer_in_thread`) and `daq_viewer_test.py:34`; then run the suites under the env var for both Qt bindings.
4. Agents: set `HOME` (and USERPROFILE) to a throwaway folder in `[tools].env` runs.
5. Later: drop plural/singular hack after one release with the migration.
