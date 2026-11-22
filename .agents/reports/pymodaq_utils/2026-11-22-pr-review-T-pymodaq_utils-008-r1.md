verdict: approve
public_api: no
behaviour_change: no
fails_without_fix: yes

# PR review T-pymodaq_utils-008 r1 (run 2026-11-22-merge-T-pymodaq_utils-008-r1)
Branch agent/pymodaq_utils/test-quality/2026-11-22 vs dev_agent: 1 commit (987dd1d78), 1 file, +9/-1, test only.

## Checks
1. Task match / drift: the diff patches `pymodaq_utils.config.get_set_local_dir` with
   `lambda user=False: local_dirs[user]`, pointing to two distinct pre-created folders under tmp_path, exactly as the
   constraint asks. Assertions (now config_test.py:288-289) unchanged. No other test touched, no reformatting.
   `merge_gate.py lint`: LINT OK (10 changed lines, product files only, trailers present).
2. Correctness: get_set_config_dir (config.py:189) looks up `get_set_local_dir` as a module global at call time, so
   the patch reaches get_config_file, copy_template_config (default dest, config.py:251) and
   load_system_config_and_update_from_user. monkeypatch restores the cached original after the test, so the
   functools.cache entry is not polluted. The test no longer writes ~/.pymodaq/config/test.toml.
3. Behaviour / API: no product file changed.
4. Tests: on dev_agent the original test fails on this machine (/etc not writable -> system dir falls back to
   ~/.pymodaq, same as user): `AssertionError: assert 'stop' in {'start': 23.0}` at config_test.py:289.
   The branch copy (config_review_tmp_test.py) passes; whole file 29 passed. Assertions are on exact keys.
   Coverage of config.py: 317 stmts, 74 missed, 77% before and after (no drop). Temp file removed, git status clean.
5. Docs: the new comment (system and user folders can coincide; get_set_local_dir is functools.cache'd) matches
   config.py:125-146 and get_set_path's PermissionError fallback (config.py:110-122).

## Findings
- none blocking.
- note: packages/pymodaq_utils/tests/config_test.py:9 adds `import pymodaq_utils.config`, outside the plan's line
  range (which was stale: the test sits at 267, not 236-261); needed for the setattr target, acceptable.

outside: packages/pymodaq_utils/tests/config_test.py:test_load_system_config|shared real folders | test_load_system_config writes into the real ~/.pymodaq config folders and mutates global TOML_DICT (already flagged out of scope by the plan; leak not reproduced here, unverified)

summary: Isolates test_nested_update_from_user from the real ~/.pymodaq folders by monkeypatching the cached get_set_local_dir to distinct tmp dirs; fixes a local failure, assertions and coverage unchanged.
