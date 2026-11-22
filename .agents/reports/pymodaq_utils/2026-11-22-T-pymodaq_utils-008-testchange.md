# T-pymodaq_utils-008: isolate test_nested_update_from_user (packages/pymodaq_utils/tests/config_test.py)

## Failing traceback BEFORE (identical on PYTEST_QT_API=pyqt6 and pyside6)
    config_dict = load_system_config_and_update_from_user(test_name)
    assert 'start' in config_dict['scan']['scan1d']
>   assert 'stop' in config_dict['scan']['scan1d']
E   AssertionError: assert 'stop' in {'start': 23.0}
    tests/config_test.py:289: AssertionError   (1 failed, 28 deselected)
Cause: system and user config folders are both ~/.pymodaq/config, so the user file overwrites the system file.

## Change
Test only: monkeypatch pymodaq_utils.config.get_set_local_dir (functools.cache'd) with a lambda returning distinct
tmp_path/system and tmp_path/user dirs (pre-created); added `import pymodaq_utils.config`. Assertions unchanged.

## Verification
- AFTER: passes on pyqt6 and pyside6; tests/config_test.py 29 passed.
- Real ~/.pymodaq/config/test.toml (mtime, size, md5) identical before/after the run.
- Coverage of config.py (config_test.py, pyside6): BEFORE 317 stmts, 74 miss, 77%; AFTER 317, 74, 77%; missing-line lists identical. No drop.

## Out of scope (not filed)
test_load_system_config (config_test.py ~123-146) shares the same coinciding folders and mutates global TOML_DICT['other'].
