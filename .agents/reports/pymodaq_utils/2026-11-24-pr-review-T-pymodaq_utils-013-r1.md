verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: n/a

# PR review T-pymodaq_utils-013 r1 (run 2026-11-24-merge-T-pymodaq_utils-013-r1)
Branch agent/pymodaq_utils/test-quality/2026-11-24, one commit 57d061ed1, 2 files, +23/-4 (tests only).

## Checks
1. Task match / drift: diff does what the plan asks: new `packages/pymodaq_utils/tests/conftest.py` with opt-in
   fixture `isolated_config_dir`; `config_test.py:125-140` test_load_system_config uses it and a deepcopy of TOML_DICT
   instead of mutating it; assertions identical (only `TOML_DICT` -> the local copy). No untouched lines reformatted.
   `merge_gate.py lint`: LINT OK (27 changed lines, product files only, trailers present).
   test_nested_update_from_user (plan "re-check"): untouched, passes on dev_agent and branch (already isolated via
   monkeypatch of get_set_local_dir), so no split task needed.
2. Correctness: `packages/pymodaq_utils/tests/conftest.py:6-18` sets PYMODAQ_CONFIG_DIR via monkeypatch (restored
   after), which `config.py:152` reads at every call; `_get_set_local_dir` (`config.py:125`) caches by
   (user, override) so the cache_clear calls are redundant but harmless; `get_set_local_dir.cache_clear` exists
   (`config.py:155`). `create_toml(template_path)` replaced by writing the copy inline: equivalent
   (`config_test.py:59-60`). Fixture is not used anywhere else; conftest adds no autouse fixture.
3. Behaviour / API: no product file changed. Nothing public changes.
4. Tests: this is an isolation/hygiene fix of the test itself; the original test passes on dev_agent (36 passed),
   so "fails without fix" is n/a. Verified the actual defect instead, with a throwaway HOME:
   - dev_agent test_load_system_config alone writes `$HOME/.pymodaq/config/test.toml` (system dir falls back to
     the user one here, /etc not writable).
   - branch test (conftest + test file copied to a temp dir under tests/, run against dev_agent code) alone writes
     nothing under `$HOME/.pymodaq`; 1 passed on pyqt6 and pyside6; whole branch file 36 passed on both.
   Test count unchanged (36). Coverage before/after diff (T-012 mandatory condition): unverified, not run; the
   change only swaps the target folder of the same calls. Temp files deleted, `git status` clean.
5. Docs: fixture docstring (`conftest.py:8-11`) matches the code (<dir>/system and <dir>/user per `config.py:127-128`,
   cache cleared before and after).

## Findings
none blocking.

outside: packages/pymodaq_utils/tests/config_test.py:TestCopy|shared real folders | the full config_test.py run still writes test.toml into the real ~/.pymodaq/config (likely TestCopy.test_copy_default/test_copy_source; which one unverified)
outside: packages/pymodaq_utils/tests/config_test.py:atexit save|logging error at exit | "--- Logging error ---" printed at interpreter exit for the 'Not saving config' warning (stream closed; unverified whether it also appears on dev_agent)

summary: Tests only: an opt-in `isolated_config_dir` conftest fixture (PYMODAQ_CONFIG_DIR) keeps test_load_system_config out of the real ~/.pymodaq folders and the test no longer mutates the shared TOML_DICT; assertions unchanged.
