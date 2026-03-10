from __future__ import annotations
import subprocess
import sys
from typing import Any, Optional, Union, get_args, TypeVar


from pymodaq.utils import data
from serializall import SerializableFactory

from pymodaq_utils.logger import set_logger


logger = set_logger('leco_utils')
JSON_TYPES = Union[str, int, float, list]

ser_factory = SerializableFactory()


## this form below is to be compatible with python <= 3.10
## for py>= 3.11 this could be written SERIALIZABLE = Union[ser_factory.get_serializables()]
SERIALIZABLE = Union[ser_factory.get_serializables()[0]]
for klass in ser_factory.get_serializables()[1:]:
    SERIALIZABLE = Union[SERIALIZABLE, klass]


def binary_serialization(
    pymodaq_object: Union[SERIALIZABLE, Any],
) -> tuple[Optional[Any], Optional[list[bytes]]]:
    """Serialize (binary) a pymodaq object, if it is not JSON compatible.

    If an object is JSON serializable, we can send it as a value to the JSON
    encoder and do not need a binary value.
    Otherwise, the JSON value is None and the serialized object is returned.

    :param pymodaq_object: the object which shall be sent via LECO protocol.
    :return: tuple of the JSON value and a list of additional payload frames.
    """
    if isinstance(pymodaq_object, get_args(JSON_TYPES)):
        return pymodaq_object, None
    return None, [SerializableFactory().get_apply_serializer(pymodaq_object)]



def binary_serialization_to_kwargs(
    pymodaq_object: Union[SERIALIZABLE, Any], data_key: str = "data"
) -> dict[str, Any]:
    """Create a dictionary of data parameters and of additional payload to send.

    This method prepares arguments for PyLECO's :meth:`Communicator.ask_rpc` method.
    In order to send a binary value as an argument `data_key` for a method, the
    argument has to be None, which is JSON describable.
    The binary data has to be sent via the `additional_payload` parameter.
    If the data can be sent as JSON, it is sent directly (`data_key`) and no
    additional frames are sent.
    """
    d, b = binary_serialization(pymodaq_object=pymodaq_object)
    return {data_key: d, "additional_payload": b}


def run_coordinator():
    command = [sys.executable, '-m', 'pyleco.coordinators.coordinator']
    subprocess.Popen(command)


def start_coordinator():
    from pyleco.directors.director import Director
    try:
        with Director(actor="COORDINATOR") as director:
            if director.communicator.namespace is None:
                run_coordinator()
            else:
                logger.info('Coordinator already running')
    except ConnectionRefusedError:
        run_coordinator()


def start_proxy_server() -> None:
    """Start a local LECO ZMQ PUB/SUB proxy on the default ports.

    Starts the pyleco proxy server in a daemon thread.  Publishers connect to
    port ``PROXY_RECEIVING_PORT`` (default 11100); subscribers connect to
    ``PROXY_RECEIVING_PORT - 1`` (default 11099).

    Safe to call multiple times; logs a warning if the port is already taken.
    """
    from pyleco.coordinators.proxy_server import start_proxy
    from pyleco.core import PROXY_RECEIVING_PORT
    try:
        start_proxy()
        logger.info(
            'Proxy server started (publishers -> %d, subscribers <- %d)',
            PROXY_RECEIVING_PORT, PROXY_RECEIVING_PORT - 1,
        )
    except TimeoutError:
        logger.warning(
            'Proxy server did not start within 1 s - it may already be running '
            '(ports %d / %d).',
            PROXY_RECEIVING_PORT, PROXY_RECEIVING_PORT - 1,
        )
    except Exception as exc:
        logger.error('Failed to start proxy server: %s', exc)
