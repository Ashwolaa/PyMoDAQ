# -*- coding: utf-8 -*-
"""
Created the 15/11/2022

@author: Sebastien Weber
"""
import pytest

from pymodaq.control_modules import utils
from pymodaq_gui.plotting.data_viewers import ViewersEnum
from pymodaq.control_modules.instruments import DAQTypesEnum


class TestDAQType:
    def test_daq_types_enum(self):
        for value in DAQTypesEnum.values():
            assert value in ViewersEnum.names()

    @pytest.mark.parametrize('daq_type_str, data_type_str, viewer_type_str', [('DAQ0D', 'Data0D', 'Viewer0D'),
                                                                              ('DAQ1D', 'Data1D', 'Viewer1D'),
                                                                              ('DAQ2D', 'Data2D', 'Viewer2D'),
                                                                              ('DAQND', 'DataND', 'ViewerND')])
    def test_to_data_type(self, daq_type_str, data_type_str, viewer_type_str):
        daq_type = DAQTypesEnum[daq_type_str]

        assert daq_type.to_daq_type() == daq_type_str
        assert daq_type.to_viewer_type() == viewer_type_str
        assert daq_type.to_data_type() == data_type_str


class TestCreateControllerParam:
    def test_no_axis_no_channel(self):
        param = utils.create_controller_param()
        names = [child['name'] for child in param['children']]
        assert names == ['controller_status', 'controller_ID']

    def test_axis_only(self):
        param = utils.create_controller_param(axis_name='X', axis_names=['X', 'Y'])
        children = {child['name']: child for child in param['children']}
        assert 'axis' in children
        assert 'channel' not in children
        assert children['axis']['limits'] == ['X', 'Y']
        assert children['axis']['value'] == 'X'

    def test_channel_only(self):
        param = utils.create_controller_param(channel_name='', channel_names=[''])
        children = {child['name']: child for child in param['children']}
        assert 'channel' in children
        assert 'axis' not in children
        assert children['channel']['limits'] == ['']
        assert children['channel']['value'] == ''

    def test_axis_and_channel(self):
        param = utils.create_controller_param(axis_name='X', axis_names=['X', 'Y'],
                                                channel_name='ChannelA',
                                                channel_names=['ChannelA', 'ChannelB'])
        children = {child['name']: child for child in param['children']}
        assert children['axis']['limits'] == ['X', 'Y']
        assert children['channel']['limits'] == ['ChannelA', 'ChannelB']
        assert children['channel']['value'] == 'ChannelA'
