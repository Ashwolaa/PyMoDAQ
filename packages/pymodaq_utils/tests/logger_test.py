# -*- coding: utf-8 -*-
"""
Created the 28/10/2022

@author: Sebastien Weber
"""
import pytest

import pymodaq_utils
from pymodaq_utils import config as config_mod
from pymodaq_utils import logger as logger_mod


def test_get_module_name():
    config_path = config_mod.get_set_config_dir()
    assert logger_mod.get_module_name(config_path) == 'config'


def test_get_base_logger():
    logger = logger_mod.set_logger('random_name')
    assert logger_mod.get_base_logger(logger).name == 'pymodaq'


def test_set_logger_non_list_debug_level_raises_config_error(monkeypatch):
    # real GlobalConfig path: the scalar 'debug_level' is read (debug_levels is not read here)
    general = logger_mod.config._configs['utils']._config['general']
    monkeypatch.setitem(general, 'debug_level', 'DEBUG')
    with pytest.raises(config_mod.ConfigError, match='DEBUG is not a list'):
        logger_mod.set_logger('non_list_debug_level')
