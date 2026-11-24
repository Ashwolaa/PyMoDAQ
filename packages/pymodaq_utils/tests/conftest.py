import pytest

from pymodaq_utils.config import get_set_local_dir


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    """Point the system and user config folders to <tmp_path>/system and <tmp_path>/user (PYMODAQ_CONFIG_DIR)

    Opt-in: tests that read or write config files of the shared real folders use it. The cache of
    get_set_local_dir is cleared before and after so no path leaks from or to other tests.
    """
    config_dir = tmp_path.joinpath('pymodaq_config')
    config_dir.mkdir()
    monkeypatch.setenv('PYMODAQ_CONFIG_DIR', str(config_dir))
    get_set_local_dir.cache_clear()
    yield config_dir
    get_set_local_dir.cache_clear()
