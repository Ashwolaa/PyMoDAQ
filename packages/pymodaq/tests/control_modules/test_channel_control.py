"""Tests for pymodaq.control_modules.channel_control.

Structure
---------
TestChannelControlDataclass  — pure-Python, no Qt
TestBuildToolbar             — requires Qt (qtbot fixture)
TestAdapters                 — requires Qt (mock DAQ_Move / DAQ_Viewer)
"""
from __future__ import annotations

import pytest

from pymodaq.control_modules.capabilities import (
    Capabilities,
    ContinuousVariable,
    DiscreteVariable,
    Observable,
    Variable,
)
from pymodaq.control_modules.channel_control import ChannelControl, build_toolbar


# ── Pure-Python / headless tests ──────────────────────────────────────────────

class TestChannelControlDataclass:
    """ChannelControl can be constructed and inspected without Qt."""

    def _dummy_query(self):
        return None

    def test_observable_channel_no_change(self):
        obs = Observable(name='spectrum', shape=(1024,))
        cc = ChannelControl(capability=obs, query=self._dummy_query, change=None)
        assert cc.capability is obs
        assert cc.change is None
        assert cc.toolbar is None

    def test_variable_channel_has_change(self):
        var = ContinuousVariable(name='position', units='mm', lo=-50.0, hi=50.0)
        called = []
        cc = ChannelControl(
            capability=var,
            query=self._dummy_query,
            change=lambda v: called.append(v),
        )
        cc.change(10.0)
        assert called == [10.0]

    def test_discrete_variable_channel(self):
        dv = DiscreteVariable(name='filter', choices=['ND1', 'ND2'])
        cc = ChannelControl(capability=dv, query=self._dummy_query,
                            change=lambda v: None)
        assert isinstance(cc.capability, DiscreteVariable)

    def test_bool_variable_channel(self):
        bv = Variable(name='shutter', dtype='bool')
        cc = ChannelControl(capability=bv, query=self._dummy_query,
                            change=lambda v: None)
        assert cc.capability.dtype == 'bool'

    def test_query_callable_is_called(self):
        called = []
        obs = Observable(name='temp')
        cc = ChannelControl(capability=obs, query=lambda: called.append(1) or 42)
        result = cc.query()
        assert result == 42
        assert called == [1]

    def test_toolbar_stored(self):
        obs = Observable(name='x')
        sentinel = object()
        cc = ChannelControl(capability=obs, query=self._dummy_query,
                            toolbar=sentinel)
        assert cc.toolbar is sentinel

    def test_update_capability_replaces_metadata(self):
        cv = ContinuousVariable(name='pos', lo=-10.0, hi=10.0, units='mm')
        cc = ChannelControl(capability=cv, query=self._dummy_query,
                            toolbar=None)
        new_cv = ContinuousVariable(name='pos', lo=-50.0, hi=50.0, units='nm')
        cc.update_capability(new_cv)
        assert cc.capability.lo == -50.0
        assert cc.capability.hi == 50.0
        assert cc.capability.units == 'nm'

    def test_update_capability_no_toolbar_does_not_raise(self):
        obs = Observable(name='temp')
        cc = ChannelControl(capability=obs, query=self._dummy_query, toolbar=None)
        cc.update_capability(Observable(name='temp', units='K'))   # must not raise

    def test_update_capability_observable_shape_stored(self):
        obs = Observable(name='frame', shape=(None, None))
        cc = ChannelControl(capability=obs, query=self._dummy_query, toolbar=None)
        cc.update_capability(Observable(name='frame', shape=(480, 640)))
        assert cc.capability.shape == (480, 640)


# ── Qt availability guard ─────────────────────────────────────────────────────

try:
    from qtpy.QtWidgets import QApplication as _QApp  # noqa: F401
    _HAS_QT = True
except Exception:
    _HAS_QT = False

_skip_no_qt = pytest.mark.skipif(not _HAS_QT, reason='No Qt backend available')


# ── Qt-dependent toolbar tests ────────────────────────────────────────────────

@_skip_no_qt
class TestBuildToolbar:
    """build_toolbar returns the correct widget structure for each capability."""

    def _widget_names(self, toolbar):
        """Collect objectNames of all widgets inside the toolbar."""
        from qtpy.QtWidgets import QWidgetAction
        names = set()
        for action in toolbar.actions():
            w = toolbar.widgetForAction(action)
            if w is not None:
                names.add(w.objectName())
        return names

    def test_observable_toolbar_has_snap_grab_stop(self, qtbot):
        obs = Observable(name='spectrum')
        tb = build_toolbar(obs)
        qtbot.addWidget(tb)
        names = self._widget_names(tb)
        assert 'snap_btn' in names
        assert 'grab_btn' in names
        assert 'stop_btn' in names

    def test_grab_btn_is_checkable(self, qtbot):
        from qtpy.QtWidgets import QPushButton
        obs = Observable(name='data')
        tb = build_toolbar(obs)
        qtbot.addWidget(tb)
        grabs = [w for w in tb.findChildren(QPushButton)
                 if w.objectName() == 'grab_btn']
        assert grabs and grabs[0].isCheckable()

    def test_continuous_toolbar_has_spinbox_go_readback(self, qtbot):
        cv = ContinuousVariable(name='position', units='mm', lo=-10.0, hi=10.0)
        tb = build_toolbar(cv)
        qtbot.addWidget(tb)
        names = self._widget_names(tb)
        assert 'value_spin' in names
        assert 'go_btn' in names
        assert 'readback_label' in names

    def test_continuous_spinbox_bounds(self, qtbot):
        from qtpy.QtWidgets import QDoubleSpinBox
        cv = ContinuousVariable(name='pos', lo=-5.0, hi=5.0)
        tb = build_toolbar(cv)
        qtbot.addWidget(tb)
        spins = tb.findChildren(QDoubleSpinBox)
        assert spins
        assert spins[0].minimum() == pytest.approx(-5.0)
        assert spins[0].maximum() == pytest.approx(5.0)

    def test_continuous_spinbox_suffix_with_units(self, qtbot):
        from qtpy.QtWidgets import QDoubleSpinBox
        cv = ContinuousVariable(name='pos', units='nm')
        tb = build_toolbar(cv)
        qtbot.addWidget(tb)
        spins = tb.findChildren(QDoubleSpinBox)
        assert spins
        assert 'nm' in spins[0].suffix()

    def test_continuous_spinbox_no_suffix_without_units(self, qtbot):
        from qtpy.QtWidgets import QDoubleSpinBox
        cv = ContinuousVariable(name='pos', units='')
        tb = build_toolbar(cv)
        qtbot.addWidget(tb)
        spins = tb.findChildren(QDoubleSpinBox)
        assert spins
        assert spins[0].suffix() == ''

    def test_discrete_toolbar_has_combo_set(self, qtbot):
        dv = DiscreteVariable(name='filter', choices=['ND1', 'ND2', 'ND4'])
        tb = build_toolbar(dv)
        qtbot.addWidget(tb)
        names = self._widget_names(tb)
        assert 'choices_combo' in names
        assert 'set_btn' in names

    def test_discrete_combo_items(self, qtbot):
        from qtpy.QtWidgets import QComboBox
        dv = DiscreteVariable(name='coupling', choices=['AC', 'DC', 'GND'])
        tb = build_toolbar(dv)
        qtbot.addWidget(tb)
        combos = tb.findChildren(QComboBox)
        assert combos
        items = [combos[0].itemText(i) for i in range(combos[0].count())]
        assert items == ['AC', 'DC', 'GND']

    def test_bool_variable_toolbar_has_toggle(self, qtbot):
        bv = Variable(name='shutter', dtype='bool')
        tb = build_toolbar(bv)
        qtbot.addWidget(tb)
        names = self._widget_names(tb)
        assert 'toggle_btn' in names

    def test_bool_toggle_is_checkable(self, qtbot):
        from qtpy.QtWidgets import QPushButton
        bv = Variable(name='shutter', dtype='bool')
        tb = build_toolbar(bv)
        qtbot.addWidget(tb)
        toggles = [w for w in tb.findChildren(QPushButton)
                   if w.objectName() == 'toggle_btn']
        assert toggles and toggles[0].isCheckable()

    def test_unconstrained_variable_falls_back_to_snap_grab_stop(self, qtbot):
        var = Variable(name='gain')   # not bool, not Continuous, not Discrete
        tb = build_toolbar(var)
        qtbot.addWidget(tb)
        names = self._widget_names(tb)
        assert 'snap_btn' in names
        assert 'grab_btn' in names
        assert 'stop_btn' in names

    # ── Callback wiring ───────────────────────────────────────────────────────

    def test_on_snap_callback_connected(self, qtbot):
        from qtpy.QtWidgets import QPushButton
        called = []
        obs = Observable(name='data')
        tb = build_toolbar(obs, on_snap=lambda: called.append(1))
        qtbot.addWidget(tb)
        snaps = [w for w in tb.findChildren(QPushButton)
                 if w.objectName() == 'snap_btn']
        snaps[0].click()
        assert called == [1]

    def test_on_change_continuous_receives_float(self, qtbot):
        from qtpy.QtWidgets import QDoubleSpinBox, QPushButton
        received = []
        cv = ContinuousVariable(name='pos', lo=0.0, hi=100.0)
        tb = build_toolbar(cv, on_change=lambda v: received.append(v))
        qtbot.addWidget(tb)
        spins = tb.findChildren(QDoubleSpinBox)
        spins[0].setValue(42.5)
        go_btns = [w for w in tb.findChildren(QPushButton)
                   if w.objectName() == 'go_btn']
        go_btns[0].click()
        assert received == [pytest.approx(42.5)]

    def test_on_change_discrete_receives_string(self, qtbot):
        from qtpy.QtWidgets import QComboBox, QPushButton
        received = []
        dv = DiscreteVariable(name='mode', choices=['fast', 'slow'])
        tb = build_toolbar(dv, on_change=lambda v: received.append(v))
        qtbot.addWidget(tb)
        combos = tb.findChildren(QComboBox)
        combos[0].setCurrentIndex(1)
        set_btns = [w for w in tb.findChildren(QPushButton)
                    if w.objectName() == 'set_btn']
        set_btns[0].click()
        assert received == ['slow']

    def test_on_change_bool_receives_bool(self, qtbot):
        from qtpy.QtWidgets import QPushButton
        received = []
        bv = Variable(name='shutter', dtype='bool')
        tb = build_toolbar(bv, on_change=lambda v: received.append(v))
        qtbot.addWidget(tb)
        toggles = [w for w in tb.findChildren(QPushButton)
                   if w.objectName() == 'toggle_btn']
        toggles[0].click()   # toggle on
        assert received == [True]
        toggles[0].click()   # toggle off
        assert received == [True, False]

    # ── Remove button ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize('cap', [
        Observable(name='x'),
        ContinuousVariable(name='pos'),
        DiscreteVariable(name='mode', choices=['a', 'b']),
        Variable(name='flag', dtype='bool'),
        Variable(name='gain'),
    ])
    def test_every_toolbar_has_remove_btn(self, qtbot, cap):
        from qtpy.QtWidgets import QPushButton
        tb = build_toolbar(cap)
        qtbot.addWidget(tb)
        removes = [w for w in tb.findChildren(QPushButton)
                   if w.objectName() == 'remove_btn']
        assert len(removes) == 1

    def test_on_remove_callback_connected(self, qtbot):
        from qtpy.QtWidgets import QPushButton
        called = []
        obs = Observable(name='data')
        tb = build_toolbar(obs, on_remove=lambda: called.append(1))
        qtbot.addWidget(tb)
        removes = [w for w in tb.findChildren(QPushButton)
                   if w.objectName() == 'remove_btn']
        removes[0].click()
        assert called == [1]

    def test_no_callbacks_does_not_raise(self, qtbot):
        """Toolbar with no callbacks connected must still construct cleanly."""
        for cap in [
            Observable(name='x'),
            ContinuousVariable(name='pos'),
            DiscreteVariable(name='mode', choices=['a']),
            Variable(name='flag', dtype='bool'),
        ]:
            tb = build_toolbar(cap)
            qtbot.addWidget(tb)

    # ── update_capability toolbar sync ───────────────────────────────────────

    def test_update_capability_syncs_spinbox_bounds(self, qtbot):
        from qtpy.QtWidgets import QDoubleSpinBox
        cv = ContinuousVariable(name='pos', lo=-10.0, hi=10.0)
        tb = build_toolbar(cv)
        qtbot.addWidget(tb)
        cc = ChannelControl(capability=cv, query=lambda: None, toolbar=tb)
        cc.update_capability(ContinuousVariable(name='pos', lo=-100.0, hi=100.0))
        spins = tb.findChildren(QDoubleSpinBox)
        assert spins[0].minimum() == pytest.approx(-100.0)
        assert spins[0].maximum() == pytest.approx(100.0)

    def test_update_capability_syncs_spinbox_suffix(self, qtbot):
        from qtpy.QtWidgets import QDoubleSpinBox
        cv = ContinuousVariable(name='pos', units='mm')
        tb = build_toolbar(cv)
        qtbot.addWidget(tb)
        cc = ChannelControl(capability=cv, query=lambda: None, toolbar=tb)
        cc.update_capability(ContinuousVariable(name='pos', units='nm'))
        spins = tb.findChildren(QDoubleSpinBox)
        assert 'nm' in spins[0].suffix()

    def test_update_capability_repopulates_combobox(self, qtbot):
        from qtpy.QtWidgets import QComboBox
        dv = DiscreteVariable(name='filter', choices=['ND1', 'ND2'])
        tb = build_toolbar(dv)
        qtbot.addWidget(tb)
        cc = ChannelControl(capability=dv, query=lambda: None, toolbar=tb)
        cc.update_capability(DiscreteVariable(name='filter', choices=['ND1', 'ND2', 'ND4']))
        combos = tb.findChildren(QComboBox)
        assert combos[0].count() == 3

    def test_update_capability_combobox_restores_selection(self, qtbot):
        from qtpy.QtWidgets import QComboBox
        dv = DiscreteVariable(name='filter', choices=['ND1', 'ND2', 'ND4'])
        tb = build_toolbar(dv)
        qtbot.addWidget(tb)
        combos = tb.findChildren(QComboBox)
        combos[0].setCurrentIndex(1)   # select 'ND2'
        cc = ChannelControl(capability=dv, query=lambda: None, toolbar=tb)
        # Update with same choices in different order — ND2 still present
        cc.update_capability(DiscreteVariable(name='filter',
                                              choices=['ND1', 'ND2', 'ND4', 'ND8']))
        combos = tb.findChildren(QComboBox)
        assert combos[0].currentText() == 'ND2'


# ── Adapter tests (mock DAQ_Move / DAQ_Viewer) ────────────────────────────────

class TestAdapters:
    """from_daq_move / from_daq_viewer build ChannelControl from legacy modules."""

    def _make_mock_move(self, units='mm', epsilon=0.01):
        """Minimal mock that satisfies from_daq_move."""
        from unittest.mock import MagicMock
        move = MagicMock()
        # Plugin that infer_capabilities can inspect
        move.plugin._controller_units = units
        move.plugin._axis_names = None
        move.plugin._epsilons = epsilon
        move.plugin.capabilities = None  # not a Capabilities instance
        move.get_actuator_value.return_value = 'dte_sentinel'
        move.move_abs.return_value = None
        # ui.toolbar is a plain object (no Qt needed for adapter construction)
        move.ui.toolbar = object()
        return move

    def _make_mock_viewer(self):
        from unittest.mock import MagicMock
        viewer = MagicMock()
        viewer.plugin._controller_units = None
        viewer.plugin._axis_names = None
        viewer.plugin._epsilons = None
        viewer.plugin.capabilities = None
        viewer.snap.return_value = 'dte_sentinel'
        viewer.ui.toolbar = object()
        return viewer

    def test_from_daq_move_capability_is_continuous_variable(self):
        move = self._make_mock_move()
        cc = ChannelControl.from_daq_move(move)
        assert isinstance(cc.capability, ContinuousVariable)

    def test_from_daq_move_units_preserved(self):
        move = self._make_mock_move(units='nm')
        cc = ChannelControl.from_daq_move(move)
        assert cc.capability.units == 'nm'

    def test_from_daq_move_epsilon_preserved(self):
        move = self._make_mock_move(epsilon=0.005)
        cc = ChannelControl.from_daq_move(move)
        assert cc.capability.epsilon == pytest.approx(0.005)

    def test_from_daq_move_query_delegates(self):
        move = self._make_mock_move()
        cc = ChannelControl.from_daq_move(move)
        result = cc.query()
        move.get_actuator_value.assert_called_once()
        assert result == 'dte_sentinel'

    def test_from_daq_move_change_delegates(self):
        move = self._make_mock_move()
        cc = ChannelControl.from_daq_move(move)
        cc.change(5.0)
        move.move_abs.assert_called_once_with(5.0)

    def test_from_daq_move_toolbar_reused(self):
        move = self._make_mock_move()
        cc = ChannelControl.from_daq_move(move)
        assert cc.toolbar is move.ui.toolbar

    def test_from_daq_move_axis_index_clamps(self):
        """axis_index beyond range clamps to last axis rather than raising."""
        move = self._make_mock_move()
        # Single-axis plugin: axis_index=5 should not raise
        cc = ChannelControl.from_daq_move(move, axis_index=5)
        assert isinstance(cc.capability, Variable)

    def test_from_daq_viewer_capability_is_observable(self):
        viewer = self._make_mock_viewer()
        cc = ChannelControl.from_daq_viewer(viewer)
        assert isinstance(cc.capability, Observable)
        assert not isinstance(cc.capability, Variable)

    def test_from_daq_viewer_change_is_none(self):
        viewer = self._make_mock_viewer()
        cc = ChannelControl.from_daq_viewer(viewer)
        assert cc.change is None

    def test_from_daq_viewer_query_delegates(self):
        viewer = self._make_mock_viewer()
        cc = ChannelControl.from_daq_viewer(viewer)
        result = cc.query()
        viewer.snap.assert_called_once()
        assert result == 'dte_sentinel'

    def test_from_daq_viewer_toolbar_reused(self):
        viewer = self._make_mock_viewer()
        cc = ChannelControl.from_daq_viewer(viewer)
        assert cc.toolbar is viewer.ui.toolbar
