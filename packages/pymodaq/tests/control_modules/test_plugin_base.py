"""Tests for pymodaq.control_modules.plugin_base."""
import pytest
from unittest.mock import MagicMock, patch
from qtpy.QtCore import QObject

from pymodaq.control_modules.plugin_base import DAQ_Plugin_base


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------

class _ConcretePlugin(DAQ_Plugin_base):
    """Minimal concrete plugin that supplies a title."""

    def __init__(self):
        QObject.__init__(self)
        self._title = 'test_plugin'


# ---------------------------------------------------------------------------
# TestDAQPluginBaseSignals
# ---------------------------------------------------------------------------

class TestDAQPluginBaseSignals:
    """Signal declarations are present on the class."""

    def test_has_capabilities_updated_signal(self):
        plugin = _ConcretePlugin()
        assert hasattr(plugin, 'capabilities_updated_signal')

    def test_has_change_done_signal(self):
        plugin = _ConcretePlugin()
        assert hasattr(plugin, 'change_done_signal')

    def test_is_qobject(self):
        plugin = _ConcretePlugin()
        assert isinstance(plugin, QObject)


# ---------------------------------------------------------------------------
# TestNewStyleFlag
# ---------------------------------------------------------------------------

class TestNewStyleFlag:
    def test_flag_is_true(self):
        assert _ConcretePlugin._new_style_plugin is True

    def test_flag_inherited_by_instance(self):
        plugin = _ConcretePlugin()
        assert plugin._new_style_plugin is True


# ---------------------------------------------------------------------------
# TestCapabilitiesProperty
# ---------------------------------------------------------------------------

class TestCapabilitiesProperty:
    def test_infers_when_none(self):
        plugin = _ConcretePlugin()
        from pymodaq.control_modules.capabilities import Capabilities
        caps = plugin.capabilities
        assert isinstance(caps, Capabilities)

    def test_setter_stores_value(self):
        plugin = _ConcretePlugin()
        from pymodaq.control_modules.capabilities import Capabilities
        new_caps = Capabilities()
        plugin.capabilities = new_caps
        assert plugin._capabilities is new_caps

    def test_setter_emits_signal(self, qtbot):
        plugin = _ConcretePlugin()
        from pymodaq.control_modules.capabilities import Capabilities
        emitted = []
        plugin.capabilities_updated_signal.connect(emitted.append)
        new_caps = Capabilities()
        plugin.capabilities = new_caps
        assert len(emitted) == 1
        assert emitted[0] is new_caps

    def test_getter_caches_result(self):
        plugin = _ConcretePlugin()
        caps1 = plugin.capabilities
        caps2 = plugin.capabilities
        assert caps1 is caps2


# ---------------------------------------------------------------------------
# TestQueryDataStub
# ---------------------------------------------------------------------------

class TestQueryDataStub:
    def test_raises_not_implemented(self):
        plugin = _ConcretePlugin()
        with pytest.raises(NotImplementedError):
            plugin.query_data()


# ---------------------------------------------------------------------------
# TestChangeToStub
# ---------------------------------------------------------------------------

class TestChangeToStub:
    def test_raises_not_implemented(self):
        plugin = _ConcretePlugin()
        with pytest.raises(NotImplementedError):
            plugin.change_to('x', 1.0)


# ---------------------------------------------------------------------------
# TestPollUntilDone
# ---------------------------------------------------------------------------

class TestPollUntilDone:
    """_poll_until_done converges and emits change_done_signal."""

    def _make_dte(self, value: float):
        """Build a minimal DataToExport with a single scalar DataActuator."""
        import numpy as np
        from pymodaq_data.data import DataToExport
        from pymodaq.utils.data import DataActuator
        dwa = DataActuator('test', data=np.array([value]))
        return DataToExport(name='test', data=[dwa])

    def test_converges_and_returns_true(self, qtbot):
        plugin = _ConcretePlugin()
        dte = self._make_dte(0.0)
        plugin.query_data = MagicMock(return_value=dte)

        done_signals = []
        plugin.change_done_signal.connect(lambda n, d: done_signals.append((n, d)))

        result = plugin._poll_until_done('x', 0.0, epsilon=0.01, timeout=1.0)
        assert result is True
        assert len(done_signals) == 1
        name, data = done_signals[0]
        assert name == 'x'
        assert data is dte

    def test_timeout_returns_false(self, qtbot):
        """When the target is never reached, returns False after timeout."""
        plugin = _ConcretePlugin()
        # Value is always far from target
        dte = self._make_dte(1000.0)
        plugin.query_data = MagicMock(return_value=dte)

        done_signals = []
        plugin.change_done_signal.connect(lambda n, d: done_signals.append((n, d)))

        result = plugin._poll_until_done('x', 0.0, epsilon=0.01,
                                         timeout=0.1, poll_interval=0.01)
        assert result is False
        # change_done_signal still emitted on timeout
        assert len(done_signals) == 1

    def test_emits_none_dte_on_query_error(self, qtbot):
        """If query_data always raises, change_done_signal is emitted with None."""
        plugin = _ConcretePlugin()
        plugin.query_data = MagicMock(side_effect=RuntimeError("boom"))

        done_signals = []
        plugin.change_done_signal.connect(lambda n, d: done_signals.append((n, d)))

        result = plugin._poll_until_done('x', 0.0, epsilon=0.01,
                                         timeout=0.1, poll_interval=0.01)
        assert result is False
        assert done_signals[0][1] is None
