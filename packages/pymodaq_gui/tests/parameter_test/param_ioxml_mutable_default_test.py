import xml.etree.ElementTree as ET

from pymodaq_gui.parameter import ioxml


XML_STRING = ('<root title="Settings" type="group">'
              '<a title="A" type="int" value="1">1</a>'
              '</root>')


def test_walk_xml_to_parameter_default_params_not_shared():
    root = ET.fromstring(XML_STRING)

    params_first = ioxml.walk_xml_to_parameter(XML_elt=root)
    params_second = ioxml.walk_xml_to_parameter(XML_elt=root)

    assert len(params_first) == 1
    assert len(params_second) == 1
    assert params_first is not params_second
