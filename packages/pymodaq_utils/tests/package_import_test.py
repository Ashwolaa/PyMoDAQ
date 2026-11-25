import importlib
from unittest import mock

import pymodaq_utils
import pymodaq_utils.logger
from pymodaq_utils.config import ConfigError


def test_config_error_while_creating_logger_is_printed_and_import_goes_on(
        isolated_config_dir, capsys):
    """A ConfigError raised by set_logger is printed, it does not abort the import."""
    def raise_config_error(*args, **kwargs):
        raise ConfigError("msg")

    # the package does `from pymodaq_utils.logger import set_logger` at (re)load time,
    # so the name must be patched on the logger module
    try:
        with mock.patch.object(pymodaq_utils.logger, 'set_logger', raise_config_error):
            capsys.readouterr()
            reloaded = importlib.reload(pymodaq_utils)
            captured = capsys.readouterr()
    finally:
        importlib.reload(pymodaq_utils)  # back to the normal module state

    assert reloaded is pymodaq_utils
    assert "msg" in captured.out
    assert "Couldn't create the local folder" not in captured.out
    # the import went on after the handler: the names defined after it exist
    assert hasattr(pymodaq_utils, 'CONFIG')
