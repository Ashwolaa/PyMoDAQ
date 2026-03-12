"""
Utils for the Director Modules

These directors correspond to the PymodaqListener
"""

from typing import Optional, Union, List

from pyleco.directors.director import Director

import pymodaq_gui.parameter.utils as putils
from pymodaq_gui.parameter import Parameter, ioxml
from pymodaq.utils.data import DataActuator
from pymodaq.utils.leco.utils import binary_serialization_to_kwargs, SerializableFactory
from pymodaq.utils.leco.rpc_method_definitions import (
    GenericMethods, MoveMethods, ViewerMethods, PymodaqActorMethods,
)

from pymodaq_gui.parameter.utils import ParameterWithPath



class GenericDirector(Director):
    """Director helper to control some Module remotely."""

    def set_remote_name(self, name: Optional[str] = None):
        """Set the remote name of the Module (i.e. where it should send responses to)."""
        self.ask_rpc(method=GenericMethods.SET_REMOTE_NAME, name=name or self.communicator.name)

    def set_info(self, param: Parameter):
        # It removes the first two parts (main_settings and detector_settings?)
        pwp = ParameterWithPath(param, putils.get_param_path(param)[2:])
        self.ask_rpc(method=GenericMethods.SET_INFO,
                     **binary_serialization_to_kwargs(pwp, data_key='parameter'))

    def get_settings(self,) -> None:
        self.ask_rpc(GenericMethods.GET_SETTINGS)


class DetectorDirector(GenericDirector):
    def send_data_grab(self) -> None:
        self.ask_rpc(ViewerMethods.GRAB)

    def send_data_snap(self) -> None:
        self.ask_rpc(ViewerMethods.SNAP)

    def stop_grab(self) -> None:
        self.ask_rpc(ViewerMethods.STOP)


class ActuatorDirector(GenericDirector):
    def move_abs(self, position: Union[list, float, DataActuator]) -> None:
        self.ask_rpc(
            MoveMethods.MOVE_ABS, **binary_serialization_to_kwargs(position, data_key="position")
        )

    def move_rel(self, position: Union[list, float, DataActuator]) -> None:
        self.ask_rpc(
            MoveMethods.MOVE_REL, **binary_serialization_to_kwargs(position, data_key="position")
        )

    def move_home(self) -> None:
        self.ask_rpc(MoveMethods.MOVE_HOME)

    def get_actuator_value(self) -> None:
        """Request that the actuator value is sent later on.

        Later the `set_data` method will be called.
        """
        # according to DAQ_Move, this supersedes "check_position"
        self.ask_rpc(MoveMethods.GET_ACTUATOR_VALUE)

    def stop_motion(self,) -> None:
        # not implemented in DAQ_Move!
        self.ask_rpc(MoveMethods.STOP_MOTION)


class PymodaqDirector(GenericDirector):
    """Base director for PymodaqActor — speaks the new query_data/change_to API.

    Both move and detector directors inherit from this class.  The distinction
    between them (Variable vs Observable) may blur over time as the
    Variable/Observable model matures.
    """

    def query_data(self, names=None, fresh: bool = True) -> Optional[str]:
        """Ask the actor to read one or more observables and publish on data channel.

        Parameters
        ----------
        names : str | list[str] | None
            Observable name(s) to read.  None = read all.
        fresh : bool
            True  → trigger new hardware acquisition (publish to ZMQ data channel).
            False → re-publish last cached value without touching hardware.

        Returns
        -------
        str or None
            Hex conversation ID of the ZMQ publish triggered by this call.
            Compare against the ``'cid'`` field in the ``'data_received'``
            ThreadCommand to identify the matching frame on the data channel.
            ``None`` if the actor had no data to publish.
        """
        return self.ask_rpc(PymodaqActorMethods.QUERY_DATA, names=names, fresh=fresh)

    def get_capabilities(self):
        """Retrieve the actor's Capabilities (observables + variables)."""
        from pymodaq.control_modules.capabilities import Capabilities
        result = self.ask_rpc(PymodaqActorMethods.GET_CAPABILITIES)
        return Capabilities.from_dict(result)

    def subscribe_settings(self) -> None:
        """Register this director to receive settings broadcasts from the actor."""
        self.ask_rpc(
            PymodaqActorMethods.SUBSCRIBE_DIRECTOR,
            name=self.communicator.full_name,
        )

    def unsubscribe_settings(self) -> None:
        """Deregister this director from settings broadcasts."""
        self.ask_rpc(
            PymodaqActorMethods.UNSUBSCRIBE_DIRECTOR,
            name=self.communicator.full_name,
        )

    def get_pymodaq_settings(self) -> Optional[str]:
        """Fetch the actor's parameter tree XML.

        Returns ``None`` if the actor has no settings.
        """
        return self.ask_rpc("get_pymodaq_settings")

    def get_grabbed_names(self) -> Optional[list]:
        """Return the names currently being grabbed by the actor in continuous mode."""
        return self.ask_rpc(PymodaqActorMethods.GET_GRABBED_NAMES)

    def set_published_names(self, names: Optional[list]) -> None:
        """Configure which names the actor publishes in continuous mode."""
        self.ask_rpc(PymodaqActorMethods.SET_PUBLISHED_NAMES, names=names)

    def get_published_names(self) -> Optional[list]:
        """Return the actor's current continuous-publish filter."""
        return self.ask_rpc(PymodaqActorMethods.GET_PUBLISHED_NAMES)


class PymodaqMoveDirector(PymodaqDirector):
    """Director for actuator-type actors (actors that expose Variables).

    Adds change_to() for writing variables.  query_data() (inherited) is used
    for polling the current value (move-done detection).
    """

    def change_to(self, name_or_dict, value=None) -> Optional[str]:
        """Write one or more variables on the actor's device.

        Parameters
        ----------
        name_or_dict : str | dict
            Variable name (str) for a single update, or a dict mapping
            variable names to new values for a multi-variable update.
        value :
            New value. Required when *name_or_dict* is a str; ignored for dict.

        Returns
        -------
        str or None
            Hex conversation ID of the auto-publish triggered after writing.
        """
        if isinstance(name_or_dict, dict):
            return self.ask_rpc(PymodaqActorMethods.CHANGE_TO, name=name_or_dict)
        return self.ask_rpc(PymodaqActorMethods.CHANGE_TO, name=name_or_dict, value=value)


class PymodaqDetectorDirector(PymodaqDirector):
    """Director for detector-type actors (actors that expose Observables).

    For a single frame use ``query_data()``.
    For continuous acquisition use ``start_grab()`` / ``stop_grab()``:
    the actor's background loop publishes frames on the ZMQ data channel
    and the director receives them passively via its ZMQ subscription.
    """

    def query_data_continuous(self, rate_hz: float = 0) -> None:
        """Tell the actor to start a continuous acquisition loop.

        Parameters
        ----------
        rate_hz:
            Target frame rate.  ``0`` (default) = as fast as the device allows.
        """
        self.ask_rpc(PymodaqActorMethods.QUERY_DATA_CONTINUOUS, rate_hz=rate_hz)

    def stop_continuous(self) -> None:
        """Tell the actor to stop its continuous acquisition loop."""
        self.ask_rpc(PymodaqActorMethods.STOP_CONTINUOUS)
