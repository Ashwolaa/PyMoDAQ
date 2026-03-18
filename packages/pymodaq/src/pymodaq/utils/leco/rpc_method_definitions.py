"""
Names of methods used between remotely controlled modules and
remote controlling director modules.
"""

from pymodaq_utils.enums import StrEnum


# Methods for all PyMoDAQ modules
class GenericMethods(StrEnum):
    SET_INFO = "set_info"
    GET_SETTINGS = "get_settings"
    SET_REMOTE_NAME = "set_remote_name"


class MoveMethods(StrEnum):
    MOVE_ABS = "move_abs"
    MOVE_REL = "move_rel"
    MOVE_HOME = "move_home"
    STOP_MOTION = "stop_motion"
    GET_ACTUATOR_VALUE = "get_actuator_value"


class ViewerMethods(StrEnum):
    GRAB = "send_data_grab"
    SNAP = "send_data_snap"
    STOP = "stop_grab"


# Director module methods
class GenericDirectorMethods(StrEnum):
    SET_DIRECTOR_SETTINGS = "set_director_settings"
    SET_DIRECTOR_INFO = "set_director_info"
    ON_GRAB_STATUS = "on_grab_status"


class MoveDirectorMethods(StrEnum):
    SET_UNITS = "set_units"
    SEND_POSITION = "send_position"
    SET_MOVE_DONE = "set_move_done"


class ViewerDirectorMethods(StrEnum):
    SET_DATA = "set_data"


class PymodaqActorMethods(StrEnum):
    QUERY_DATA            = "query_data"
    CHANGE_TO             = "change_to"
    STOP                  = "stop"
    GET_ACQUISITION_STATUS = "get_acquisition_status"
    GET_READ_LIST         = "get_read_list"
    GET_CAPABILITIES      = "get_capabilities"
    SUBSCRIBE_DIRECTOR    = "subscribe_director"
    UNSUBSCRIBE_DIRECTOR  = "unsubscribe_director"
    GET_ACTOR_PUB_TOPIC   = "get_actor_pub_topic"
    GET_ROLE              = "get_role"
    SHUTDOWN              = "shutdown"
    # Deprecated aliases (kept for one release cycle):
    QUERY_DATA_CONTINUOUS = "query_data_continuous"
    STOP_CONTINUOUS       = "stop_continuous"
    GET_GRABBED_NAMES     = "get_grabbed_names"
    SET_PUBLISHED_NAMES   = "set_published_names"
    GET_PUBLISHED_NAMES   = "get_published_names"


class DirectorRPCMethods(StrEnum):
    GET_ROLE   = "get_role"
    DISCONNECT = "disconnect"
