"""Tests for PymodaqDirector, PymodaqMoveDirector, PymodaqDetectorDirector.

Pure Python — no Qt, no real LECO network.
Uses pyleco's FakeDirector to mock transport.
"""
import pytest
from pyleco.test import FakeDirector, FakeCommunicator

from pymodaq.utils.leco.actor import PymodaqActor
from pymodaq.control_modules.capabilities import (
    Capabilities,
    Observable,
    ContinuousVariable,
)
from pymodaq.utils.leco.director_utils import (
    PymodaqDirector,
    PymodaqMoveDirector,
    PymodaqDetectorDirector,
)


# ── Fake director helpers ───────────────────────────────────────────────────

class FakePymodaqDirector(FakeDirector, PymodaqDirector):
    pass


class FakePymodaqMoveDirector(FakeDirector, PymodaqMoveDirector):
    pass


class FakePymodaqDetectorDirector(FakeDirector, PymodaqDetectorDirector):
    pass


@pytest.fixture
def move_director():
    d = FakePymodaqMoveDirector(remote_class=PymodaqActor)
    d.communicator = FakeCommunicator("N.Director")
    d.return_value = None
    return d


@pytest.fixture
def detector_director():
    d = FakePymodaqDetectorDirector(remote_class=PymodaqActor)
    d.communicator = FakeCommunicator("N.Director")
    d.return_value = None
    return d


@pytest.fixture
def base_director():
    d = FakePymodaqDirector(remote_class=PymodaqActor)
    d.communicator = FakeCommunicator("N.Director")
    d.return_value = None
    return d


# ── query_data tests ────────────────────────────────────────────────────────

def test_query_data_no_args(base_director):
    base_director.query_data()
    assert base_director.method == "query_data"
    assert base_director.kwargs == {"names": None, "fresh": True}


def test_query_data_single_name(base_director):
    base_director.query_data("frame")
    assert base_director.method == "query_data"
    assert base_director.kwargs == {"names": "frame", "fresh": True}


def test_query_data_fresh_false(base_director):
    base_director.query_data(fresh=False)
    assert base_director.method == "query_data"
    assert base_director.kwargs == {"names": None, "fresh": False}


# ── change_to tests ─────────────────────────────────────────────────────────

def test_change_to_scalar(move_director):
    move_director.change_to("position", 10.0)
    assert move_director.method == "change_to"
    assert move_director.kwargs == {"name": "position", "value": 10.0}


def test_change_to_list(move_director):
    move_director.change_to(["x", "y"], [1.0, 2.0])
    assert move_director.method == "change_to"
    assert move_director.kwargs == {"name": ["x", "y"], "value": [1.0, 2.0]}


# ── get_capabilities test ───────────────────────────────────────────────────

def test_get_capabilities_returns_capabilities(base_director):
    caps = Capabilities(
        observables=[Observable("frame", shape=(64,), dtype="float64")],
        variables=[ContinuousVariable("pos", shape=(), dtype="float64")],
    )
    base_director.return_value = caps.to_dict()
    result = base_director.get_capabilities()
    assert isinstance(result, Capabilities)
    assert len(result.observables) == 1
    assert result.observables[0].name == "frame"
    assert len(result.variables) == 1
    assert result.variables[0].name == "pos"


# ── subscribe / unsubscribe tests ───────────────────────────────────────────

def test_subscribe_settings_sends_full_name(base_director):
    base_director.subscribe_settings()
    assert base_director.method == "subscribe_director"
    assert base_director.kwargs == {"name": base_director.communicator.full_name}


def test_unsubscribe_settings(base_director):
    base_director.unsubscribe_settings()
    assert base_director.method == "unsubscribe_director"
    assert base_director.kwargs == {"name": base_director.communicator.full_name}


# ── structural tests ────────────────────────────────────────────────────────

def test_move_director_has_change_to():
    assert hasattr(PymodaqMoveDirector, "change_to")


def test_detector_director_no_change_to():
    assert not hasattr(PymodaqDetectorDirector, "change_to")


def test_both_inherit_pymodaq_director():
    assert issubclass(PymodaqMoveDirector, PymodaqDirector)
    assert issubclass(PymodaqDetectorDirector, PymodaqDirector)
