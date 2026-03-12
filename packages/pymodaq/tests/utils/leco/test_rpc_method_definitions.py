import pytest
from pyleco.json_utils.json_objects import Request

try:
    from pymodaq.utils.leco.daq_move_LECODirector import DAQ_Move_LECODirector
    from pymodaq.utils.leco.daq_xDviewer_LECODirector import DAQ_xDViewer_LECODirector
    _HAS_QT_DIRECTORS = True
except Exception:
    _HAS_QT_DIRECTORS = False

from pymodaq.utils.leco.rpc_method_definitions import (
    GenericDirectorMethods,
    MoveDirectorMethods,
    ViewerDirectorMethods,
    DirectorRPCMethods,
)

_skip_qt = pytest.mark.skipif(
    not _HAS_QT_DIRECTORS,
    reason="Qt-based director plugins unavailable (no display or missing Qt install)",
)

discover_string = Request(1, "rpc.discover").model_dump_json()


@_skip_qt
class Test_MoveDirector_methods:
    @pytest.fixture(scope="class")
    def methods(self) -> list[str]:
        dir_class = DAQ_Move_LECODirector
        dir_class.start_timer = print  # type: ignore
        dir = dir_class()
        response = dir.listener.message_handler.rpc.process_request(discover_string)
        assert response is not None
        result = dir.listener.message_handler.rpc_generator.get_result_from_response(response)
        methods = result["methods"]
        dir.listener.stop_listen()
        return [item["name"] for item in methods]

    @pytest.mark.parametrize("method", GenericDirectorMethods)
    def test_generic_methods_are_present(self, method, methods):
        assert method in methods

    @pytest.mark.parametrize("method", MoveDirectorMethods)
    def test_move_methods_are_present(self, method, methods):
        assert method in methods


@_skip_qt
class Test_ViewerDirector_methods:
    @pytest.fixture(scope="class")
    def methods(self) -> list[str]:
        dir_class = DAQ_xDViewer_LECODirector
        dir_class.start_timer = print  # type: ignore
        dir = dir_class()
        response = dir.listener.message_handler.rpc.process_request(discover_string)
        assert response is not None
        result = dir.listener.message_handler.rpc_generator.get_result_from_response(response)
        methods = result["methods"]
        return [item["name"] for item in methods]

    @pytest.mark.parametrize("method", GenericDirectorMethods)
    def test_generic_methods_are_present(self, method, methods):
        assert method in methods

    @pytest.mark.parametrize("method", ViewerDirectorMethods)
    def test_move_methods_are_present(self, method, methods):
        assert method in methods


class TestDirectorRPCMethods:
    """Phase 0 — DirectorRPCMethods enum exists and contains expected values."""

    def test_get_role_value(self):
        assert DirectorRPCMethods.GET_ROLE == "get_role"

    def test_disconnect_value(self):
        assert DirectorRPCMethods.DISCONNECT == "disconnect"

    def test_all_members(self):
        assert set(DirectorRPCMethods) == {
            DirectorRPCMethods.GET_ROLE,
            DirectorRPCMethods.DISCONNECT,
        }


@_skip_qt
class TestMoveDirectorPhase0Methods:
    """Phase 0 — get_role and disconnect are registered on DAQ_Move_LECODirector."""

    @pytest.fixture(scope="class")
    def methods(self) -> list[str]:
        dir_class = DAQ_Move_LECODirector
        dir_class.start_timer = print  # type: ignore
        d = dir_class()
        response = d.listener.message_handler.rpc.process_request(discover_string)
        assert response is not None
        result = d.listener.message_handler.rpc_generator.get_result_from_response(response)
        d.listener.stop_listen()
        return [item["name"] for item in result["methods"]]

    def test_get_role_registered(self, methods):
        assert "get_role" in methods

    def test_disconnect_registered(self, methods):
        assert "disconnect" in methods


@_skip_qt
class TestViewerDirectorPhase0Methods:
    """Phase 0 — get_role and disconnect are registered on DAQ_xDViewer_LECODirector."""

    @pytest.fixture(scope="class")
    def methods(self) -> list[str]:
        dir_class = DAQ_xDViewer_LECODirector
        dir_class.start_timer = print  # type: ignore
        d = dir_class()
        response = d.listener.message_handler.rpc.process_request(discover_string)
        assert response is not None
        result = d.listener.message_handler.rpc_generator.get_result_from_response(response)
        return [item["name"] for item in result["methods"]]

    def test_get_role_registered(self, methods):
        assert "get_role" in methods

    def test_disconnect_registered(self, methods):
        assert "disconnect" in methods

