
from unittest.mock import MagicMock, patch

from pyleco.core.message import Message, MessageTypes
from pyleco.json_utils.json_objects import ErrorResponse, ResultResponse, Request
from pyleco.json_utils.errors import RECEIVER_UNKNOWN, NODE_UNKNOWN
from pyleco.test import FakeCommunicator
import pytest

from pymodaq.utils.leco.rpc_method_definitions import GenericMethods, MoveMethods, ViewerMethods

try:
    from pymodaq.utils.leco.pymodaq_listener import ActorListener, DataSubscriberHandler
except Exception:
    pytest.skip("Requires Qt-laden pymodaq modules", allow_module_level=True)


name = "listener"

@pytest.fixture
def actorListener() -> ActorListener:
    listener = ActorListener(name=name)  # , context=FakeContext())  # type: ignore
    listener.communicator = FakeCommunicator(name=name)  # type: ignore[assign]
    return listener


discover_string = Request(1, "rpc.discover").model_dump_json()


class Test_methods_presence:
    @pytest.fixture(scope="class")
    def methods(self) -> list[str]:
        actorListener = ActorListener(name=name)
        actorListener.start_listen()
        response = actorListener.message_handler.rpc.process_request(discover_string)
        assert response is not None
        result = actorListener.message_handler.rpc_generator.get_result_from_response(response)
        methods = result["methods"]
        actorListener.stop_listen()
        return [item["name"] for item in methods]

    @pytest.mark.parametrize("method", GenericMethods)
    def test_generic_methods_are_present(self, method, methods):
        assert method in methods

    @pytest.mark.parametrize("method", MoveMethods)
    def test_move_methods_are_present(self, method, methods):
        assert method in methods

    @pytest.mark.parametrize("method", ViewerMethods)
    def test_viewer_methods_are_present(self, method, methods):
        assert method in methods


class TestSendRPCToRemote:
    remote_name = "receiver"

    def test_send_message_successfully(self, actorListener: ActorListener):
        actorListener.set_remote_name(self.remote_name)
        actorListener.communicator._r = [  # type: ignore[assign]
            Message(
                name,
                self.remote_name,
                message_type=MessageTypes.JSON,
                data=ResultResponse(1, None),
            )
        ]
        actorListener.send_rpc_message_to_remote("whatever")
        sent: Message = actorListener.communicator._s[0]  # type: ignore
        expected_sent = Message(
            self.remote_name,
            name,
            data=Request(1, "whatever"),
            header=sent.header,
        )
        assert expected_sent == sent
        assert self.remote_name in actorListener.remote_names

    @pytest.mark.parametrize("error", (RECEIVER_UNKNOWN, NODE_UNKNOWN))
    def test_unreachable_receiver_removes_receiver(self, actorListener: ActorListener, error):
        actorListener.set_remote_name(self.remote_name)
        actorListener.communicator._r = [  # type: ignore[assign]
            Message(
                name,
                self.remote_name,
                message_type=MessageTypes.JSON,
                data=ErrorResponse(None, error=error),
            )
        ]
        actorListener.send_rpc_message_to_remote("whatever")
        assert self.remote_name not in actorListener.remote_names


class TestDataSubscriberSignalSeparation:
    """Verify that ZMQ data frames are routed to data_signal, NOT cmd_signal."""

    TOPIC = "localhost.stage"

    @pytest.fixture
    def handler_with_mocks(self):
        """DataSubscriberHandler with mocked signals, ZMQ __init__ bypassed."""
        handler = object.__new__(DataSubscriberHandler)
        mock_signals = MagicMock()
        handler.signals = mock_signals
        return handler, mock_signals

    def test_data_signal_emitted_with_topic_and_dte(self, handler_with_mocks):
        """handle_subscription_message emits data_signal(topic, dte)."""
        handler, mock_signals = handler_with_mocks
        fake_dte = MagicMock(name="dte")

        msg = MagicMock()
        msg.topic = self.TOPIC.encode()
        msg.payload = [b"fake_bytes"]

        with patch(
            "pymodaq.utils.leco.pymodaq_listener.SerializableFactory"
        ) as mock_factory:
            mock_factory.return_value.get_apply_deserializer.return_value = fake_dte
            handler.handle_subscription_message(msg)

        mock_signals.data_signal.emit.assert_called_once_with(self.TOPIC, fake_dte)

    def test_cmd_signal_not_emitted_on_data_frame(self, handler_with_mocks):
        """handle_subscription_message must NOT touch cmd_signal for data frames."""
        handler, mock_signals = handler_with_mocks
        fake_dte = MagicMock(name="dte")

        msg = MagicMock()
        msg.topic = self.TOPIC.encode()
        msg.payload = [b"fake_bytes"]

        with patch(
            "pymodaq.utils.leco.pymodaq_listener.SerializableFactory"
        ) as mock_factory:
            mock_factory.return_value.get_apply_deserializer.return_value = fake_dte
            handler.handle_subscription_message(msg)

        mock_signals.cmd_signal.emit.assert_not_called()

    def test_empty_payload_skipped(self, handler_with_mocks):
        """Empty payload must not emit either signal."""
        handler, mock_signals = handler_with_mocks

        msg = MagicMock()
        msg.topic = self.TOPIC.encode()
        msg.payload = []

        handler.handle_subscription_message(msg)

        mock_signals.data_signal.emit.assert_not_called()
        mock_signals.cmd_signal.emit.assert_not_called()

    def test_deserialization_error_does_not_emit(self, handler_with_mocks):
        """If deserialization raises, neither signal must be emitted."""
        handler, mock_signals = handler_with_mocks

        msg = MagicMock()
        msg.topic = self.TOPIC.encode()
        msg.payload = [b"garbage"]

        with patch(
            "pymodaq.utils.leco.pymodaq_listener.SerializableFactory"
        ) as mock_factory:
            mock_factory.return_value.get_apply_deserializer.side_effect = ValueError("bad data")
            handler.handle_subscription_message(msg)

        mock_signals.data_signal.emit.assert_not_called()
        mock_signals.cmd_signal.emit.assert_not_called()
