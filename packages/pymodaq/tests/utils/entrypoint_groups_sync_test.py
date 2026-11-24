"""The plugin entry point groups are listed twice (plugin checker and daq_utils): they must not drift."""
from pymodaq_utils.plugin_tools import checks

from pymodaq.utils import daq_utils


def test_entrypoint_groups_match_between_checks_and_daq_utils():
    checks_groups = checks.ENTRYPOINT_GROUPS + checks.OPTIONAL_ENTRYPOINT_GROUPS
    assert len(set(checks_groups)) == len(checks_groups)
    assert set(checks_groups) == set(daq_utils.PLUGIN_ENTRYPOINT_GROUPS)
