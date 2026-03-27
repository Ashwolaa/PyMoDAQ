"""Per-channel control unit for capabilities-driven DAQ modules.

:class:`ChannelControl` is the lightweight row unit used by the compact dock
manager.  One instance per :class:`~pymodaq.control_modules.capabilities.Observable`
or :class:`~pymodaq.control_modules.capabilities.Variable` declared in a
plugin's :class:`~pymodaq.control_modules.capabilities.Capabilities`.

Toolbar factory
---------------
:func:`build_toolbar` creates an appropriate :class:`~qtpy.QtWidgets.QToolBar`
from a capability descriptor:

- :class:`Observable`         → Snap / Grab(toggle) / Stop
- :class:`ContinuousVariable` → name label + spinbox + Go + readback label
- :class:`DiscreteVariable`   → name label + combobox + Set
- :class:`Variable` (bool)    → name label + toggle button
- :class:`Variable` (other)   → falls back to Observable toolbar (snap/grab/stop)

Backward-compat adapters
------------------------
:meth:`ChannelControl.from_daq_move` and :meth:`ChannelControl.from_daq_viewer`
wrap existing :class:`~pymodaq.control_modules.daq_move.DAQ_Move` and
:class:`~pymodaq.control_modules.daq_viewer.DAQ_Viewer` instances so they can
be registered in the new compact-dock API without any plugin changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from pymodaq.control_modules.capabilities import (
    Capabilities,
    ContinuousVariable,
    DiscreteVariable,
    Observable,
    Variable,
    infer_capabilities,
)

if TYPE_CHECKING:
    from qtpy.QtWidgets import QToolBar
    from pymodaq.control_modules.daq_move import DAQ_Move
    from pymodaq.control_modules.daq_viewer import DAQ_Viewer
    from pymodaq_data.data import DataToExport


__all__ = ['ChannelControl', 'build_toolbar']


# Interactive widget objectNames created by build_toolbar that should be
# disabled when the dock-level lock is active.
_LOCKABLE_OBJECT_NAMES: frozenset[str] = frozenset({
    'go_btn', 'set_btn', 'toggle_btn',
    'snap_btn', 'grab_btn', 'stop_btn',
    'value_spin', 'choices_combo',
})


# ── ChannelControl ────────────────────────────────────────────────────────────

@dataclass
class ChannelControl:
    """Lightweight per-channel control unit.

    One :class:`ChannelControl` per
    :class:`~pymodaq.control_modules.capabilities.Observable` or
    :class:`~pymodaq.control_modules.capabilities.Variable` declared in a
    plugin's Capabilities.

    Parameters
    ----------
    capability :
        The Observable or Variable this channel represents.  Determines the
        toolbar style and whether *change* is meaningful.
    query :
        Zero-argument callable that reads the current value.  Must return a
        :class:`~pymodaq_data.data.DataToExport`.
    change :
        Single-argument callable that writes a new value.  ``None`` for pure
        Observables (read-only channels).
    toolbar :
        The :class:`~qtpy.QtWidgets.QToolBar` row shown in the compact dock.
        Build it with :func:`build_toolbar`, or supply the existing toolbar
        from a legacy module via the :meth:`from_daq_move` /
        :meth:`from_daq_viewer` adapters.
    """

    capability: Observable          # Variable is a subclass of Observable
    query: Callable[[], 'DataToExport']
    change: Callable[[Any], None] | None = None
    toolbar: Any = None             # QToolBar; Any avoids a hard Qt import here

    # ── Lock ──────────────────────────────────────────────────────────────────

    def set_locked(self, locked: bool) -> None:
        """Enable/disable all interactive widgets in the toolbar.

        Called by the dock-level lock mechanism.  Finds every widget whose
        ``objectName`` is in :data:`_LOCKABLE_OBJECT_NAMES` and sets its
        enabled state accordingly.

        Parameters
        ----------
        locked :
            True to disable all interactive controls; False to re-enable them.
        """
        if self.toolbar is None:
            return
        from qtpy.QtWidgets import QWidget
        for widget in self.toolbar.findChildren(QWidget):
            if widget.objectName() in _LOCKABLE_OBJECT_NAMES:
                widget.setEnabled(not locked)

    # ── Capability updates ────────────────────────────────────────────────────

    def update_capability(self, new_cap: Observable) -> None:
        """Refine this channel's metadata in-place and sync the toolbar.

        Called by the framework when the plugin emits
        ``capabilities_updated_signal`` and the channel (identified by
        ``new_cap.name``) still exists in the new capabilities — i.e. it is an
        in-place refinement, not a structural add/remove.

        What is updated:

        * :class:`~pymodaq.control_modules.capabilities.ContinuousVariable`
          — spinbox minimum/maximum, suffix (units).
        * :class:`~pymodaq.control_modules.capabilities.DiscreteVariable`
          — combobox items repopulated from new ``choices``.
        * :class:`~pymodaq.control_modules.capabilities.Observable` shape
          — stored on ``self.capability`` only; forwarded to ``DAQ_Monitor``
          by the framework (not the toolbar).

        The toolbar widget type is **not** changed here.  If the capability
        *kind* changes (e.g. Continuous → Discrete) the framework must remove
        this :class:`ChannelControl` and add a fresh one instead.

        Parameters
        ----------
        new_cap :
            Updated capability descriptor for this channel.  Must have the
            same ``name`` as the current ``self.capability``.
        """
        self.capability = new_cap
        if self.toolbar is None:
            return
        self._sync_toolbar(new_cap)

    def _sync_toolbar(self, cap: Observable) -> None:
        """Push updated metadata from *cap* into the existing toolbar widgets."""
        from qtpy.QtWidgets import QDoubleSpinBox, QComboBox

        if isinstance(cap, ContinuousVariable):
            spins = self.toolbar.findChildren(QDoubleSpinBox)
            if spins:
                spin = spins[0]
                if cap.lo is not None:
                    spin.setMinimum(cap.lo)
                else:
                    spin.setMinimum(-1e12)
                if cap.hi is not None:
                    spin.setMaximum(cap.hi)
                else:
                    spin.setMaximum(1e12)
                suffix = f'  {cap.units}' if cap.units else ''
                spin.setSuffix(suffix)

        elif isinstance(cap, DiscreteVariable):
            combos = self.toolbar.findChildren(QComboBox)
            if combos:
                combo = combos[0]
                current = combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                for choice in cap.choices:
                    combo.addItem(str(choice))
                # Restore previous selection if still valid
                idx = combo.findText(current)
                combo.setCurrentIndex(max(idx, 0))
                combo.blockSignals(False)

    # ── Backward-compat adapters ──────────────────────────────────────────────

    @classmethod
    def from_daq_move(cls, daq_move: 'DAQ_Move',
                      axis_index: int = 0) -> 'ChannelControl':
        """Wrap an existing :class:`~pymodaq.control_modules.daq_move.DAQ_Move`.

        Reuses the module's existing toolbar and delegates *query* /
        *change* to the module's existing public methods.  No plugin changes
        required.

        Parameters
        ----------
        daq_move :
            An initialised ``DAQ_Move`` instance.
        axis_index :
            Which axis to represent when the module controls multiple axes.
            Defaults to 0 (first / only axis).

        Notes
        -----
        Full threading integration (routing through ``DAQ_HardwareWorker``) is
        deferred to Phase 3.  These callables invoke the existing Qt-signal
        machinery unchanged.
        """
        plugin = getattr(daq_move, 'plugin', daq_move)
        caps = infer_capabilities(plugin)
        if caps.variables:
            variable: Variable = caps.variables[
                min(axis_index, len(caps.variables) - 1)
            ]
        else:
            variable = Variable(name='position')

        return cls(
            capability=variable,
            query=lambda: daq_move.get_actuator_value(),
            change=lambda v: daq_move.move_abs(v),
            toolbar=daq_move.ui.toolbar,
        )

    @classmethod
    def from_daq_viewer(cls, daq_viewer: 'DAQ_Viewer') -> 'ChannelControl':
        """Wrap an existing :class:`~pymodaq.control_modules.daq_viewer.DAQ_Viewer`.

        Reuses the module's existing toolbar.  *query* triggers a single snap;
        continuous grab is handled by the existing module toolbar buttons.

        Notes
        -----
        Full ``DAQ_Monitor`` integration is deferred to Phase 5.
        """
        plugin = getattr(daq_viewer, 'plugin', daq_viewer)
        caps = infer_capabilities(plugin)
        observable = caps.observables[0] if caps.observables else Observable(name='data')

        return cls(
            capability=observable,
            query=lambda: daq_viewer.snap(),
            change=None,
            toolbar=daq_viewer.ui.toolbar,
        )


# ── Toolbar factory ───────────────────────────────────────────────────────────

def build_toolbar(
    capability: Observable,
    *,
    on_snap: Callable[[], None] | None = None,
    on_grab: Callable[[bool], None] | None = None,
    on_stop: Callable[[], None] | None = None,
    on_change: Callable[[Any], None] | None = None,
    on_remove: Callable[[], None] | None = None,
) -> 'QToolBar':
    """Build a :class:`~qtpy.QtWidgets.QToolBar` suited to *capability*.

    The toolbar style is determined by the capability type:

    * :class:`~pymodaq.control_modules.capabilities.Observable` (and
      unconstrained :class:`~pymodaq.control_modules.capabilities.Variable`)
      → **Snap** button + **Grab** toggle + **Stop** button.
    * :class:`~pymodaq.control_modules.capabilities.ContinuousVariable`
      → name label + :class:`~qtpy.QtWidgets.QDoubleSpinBox` + **Go** button
      + readback label.
    * :class:`~pymodaq.control_modules.capabilities.DiscreteVariable`
      → name label + :class:`~qtpy.QtWidgets.QComboBox` + **Set** button.
    * :class:`~pymodaq.control_modules.capabilities.Variable` with
      ``dtype == 'bool'`` → name label + checkable toggle button.

    Parameters
    ----------
    capability :
        Drives the toolbar template.
    on_snap :
        Connected to the Snap button (Observable toolbar).
    on_grab :
        Connected to the Grab toggle (Observable toolbar); receives *checked*.
    on_stop :
        Connected to the Stop button (Observable toolbar).
    on_change :
        Connected to Go / Set / toggle depending on toolbar type; receives the
        new value (``float`` for Continuous, ``str`` for Discrete, ``bool``
        for bool Variable).
    on_remove :
        Connected to the ``×`` remove button present on every toolbar.
        The framework decides whether "remove" means *hide* (session-only,
        capability unchanged) or *unexpose* (remove capability from plugin);
        this callback simply signals intent.

    Returns
    -------
    QToolBar
    """
    from qtpy.QtWidgets import (
        QToolBar, QLabel, QDoubleSpinBox, QComboBox, QPushButton,
    )

    toolbar = QToolBar()
    toolbar.setFloatable(False)
    toolbar.setMovable(True)

    display_name = capability.label or capability.name

    if isinstance(capability, DiscreteVariable):
        toolbar.addWidget(QLabel(display_name))
        combo = QComboBox()
        combo.setObjectName('choices_combo')
        for choice in capability.choices:
            combo.addItem(str(choice))
        toolbar.addWidget(combo)
        btn = QPushButton('Set')
        btn.setObjectName('set_btn')
        if on_change is not None:
            btn.clicked.connect(lambda: on_change(combo.currentText()))
        toolbar.addWidget(btn)

    elif isinstance(capability, ContinuousVariable):
        toolbar.addWidget(QLabel(display_name))
        spinbox = QDoubleSpinBox()
        spinbox.setObjectName('value_spin')
        spinbox.setDecimals(6)
        if capability.lo is not None:
            spinbox.setMinimum(capability.lo)
        else:
            spinbox.setMinimum(-1e12)
        if capability.hi is not None:
            spinbox.setMaximum(capability.hi)
        else:
            spinbox.setMaximum(1e12)
        if capability.units:
            spinbox.setSuffix(f'  {capability.units}')
        toolbar.addWidget(spinbox)
        go_btn = QPushButton('Go')
        go_btn.setObjectName('go_btn')
        if on_change is not None:
            go_btn.clicked.connect(lambda: on_change(spinbox.value()))
        toolbar.addWidget(go_btn)
        readback = QLabel('—')
        readback.setObjectName('readback_label')
        readback.setMinimumWidth(60)
        toolbar.addWidget(readback)

    elif isinstance(capability, Variable) and capability.dtype == 'bool':
        toolbar.addWidget(QLabel(display_name))
        toggle = QPushButton(display_name)
        toggle.setObjectName('toggle_btn')
        toggle.setCheckable(True)
        if on_change is not None:
            toggle.toggled.connect(on_change)
        toolbar.addWidget(toggle)

    else:
        # Observable or unconstrained Variable → snap / grab / stop
        toolbar.addWidget(QLabel(display_name))
        snap_btn = QPushButton('Snap')
        snap_btn.setObjectName('snap_btn')
        if on_snap is not None:
            snap_btn.clicked.connect(on_snap)
        toolbar.addWidget(snap_btn)

        grab_btn = QPushButton('Grab')
        grab_btn.setObjectName('grab_btn')
        grab_btn.setCheckable(True)
        if on_grab is not None:
            grab_btn.toggled.connect(on_grab)
        toolbar.addWidget(grab_btn)

        stop_btn = QPushButton('Stop')
        stop_btn.setObjectName('stop_btn')
        if on_stop is not None:
            stop_btn.clicked.connect(on_stop)
        toolbar.addWidget(stop_btn)

    # ── Remove button — present on every toolbar type ─────────────────────────
    toolbar.addSeparator()
    remove_btn = QPushButton('×')
    remove_btn.setObjectName('remove_btn')
    remove_btn.setToolTip('Remove this channel from the dock')
    remove_btn.setFixedWidth(20)
    if on_remove is not None:
        remove_btn.clicked.connect(on_remove)
    toolbar.addWidget(remove_btn)

    return toolbar
