"""PymodaqActor GUI — hardware-side launcher for PymodaqActor.

Runs on the **acquisition computer** (hardware side).  Lets the user:

1. Select a hardware plugin class (must implement the actor device interface:
   ``connect()``, ``close()``, ``read(names=None) -> DataToExport``,
   ``write(name, value) -> None``).
2. Browse / configure its default settings in the Settings dock.
3. Click **Init Instrument** — instantiates ``plugin_class(parent=None)`` to
   confirm the class loads cleanly and populate the settings tree.
   No hardware is touched here; ``ini_stage`` / ``ini_detector`` are *not* called
   (those belong to the director side, i.e. DAQ_Move / DAQ_Viewer).
4. Click **Start Actor** — passes the class directly to :class:`PymodaqActor`
   (pyleco calls ``device_class()`` internally in ``connect()``), then calls
   ``actor.listen()`` in a daemon thread.
5. Open :class:`DAQ_Move_LECODirector` / :class:`DAQ_xDViewer_LECODirector`
   windows for each capability the actor declares.  Those windows handle their own
   ``ini_stage`` / ``ini_detector`` lifecycle when connecting to the actor.

Thread model
------------
Main thread (Qt)
└── PymodaqActorGUI  (CustomApp + ParameterManager)
    │  Owns all GUI state.  Drives the worker via cross-thread signals.
    └── QThread: worker_thread
        └── ActorWorker  (QObject)
            ├── init_instrument() — load class, instantiate for settings display
            └── start_actor()    — PymodaqActor(device_class=plugin_class) + listen()
"""
from __future__ import annotations

import importlib
import logging
import threading
from typing import Optional

from qtpy import QtWidgets
from qtpy.QtCore import QMetaObject, QObject, QThread, Signal, Slot, Qt

from pymodaq_gui.parameter import Parameter, ParameterTree
from pymodaq_gui.qt_utils import mkQApp
from pymodaq_gui.utils.custom_app import CustomApp
from pymodaq_gui.utils.dock import Dock
from pymodaq_gui.utils.widgets.qled import QLED
from pymodaq_utils.utils import ThreadCommand
from pyleco.core import COORDINATOR_PORT

from pymodaq.control_modules.capabilities import (
    Capabilities, ContinuousVariable, DiscreteVariable,
)
from pymodaq.utils.leco.actor import PymodaqActor

logger = logging.getLogger(__name__)

# ── Plugin registry (guarded — raises if no plugins installed) ─────────────────
try:
    from pymodaq.control_modules.instruments import ACTUATOR_TYPES, ACTUATOR_NAMES, DET_TYPES
except Exception as _exc:
    logger.warning("No plugins installed: %s", _exc)
    ACTUATOR_TYPES = []
    ACTUATOR_NAMES = []
    DET_TYPES = {'DAQ0D': [], 'DAQ1D': [], 'DAQ2D': []}


# ── Plugin class loader ────────────────────────────────────────────────────────

def _load_plugin_class(plugin_type: str, plugin_name: str):
    """Return the plugin class for *plugin_type* / *plugin_name*.

    Parameters
    ----------
    plugin_type:
        ``'Actuator'``, ``'DAQ0D'``, ``'DAQ1D'``, or ``'DAQ2D'``.
    plugin_name:
        Name as listed in ``ACTUATOR_NAMES`` or ``DET_TYPES``.

    Raises
    ------
    ValueError
        If the plugin is not found in the registry.
    AttributeError
        If the expected class is not in the plugin module.
    """
    if plugin_type == 'Actuator':
        info = next((d for d in ACTUATOR_TYPES if d['name'] == plugin_name), None)
        if info is None:
            raise ValueError(f"Unknown actuator plugin: {plugin_name!r}")
        cls_name = f'DAQ_Move_{plugin_name}'
    else:
        det_list = DET_TYPES.get(plugin_type, [])
        info = next((d for d in det_list if d['name'] == plugin_name), None)
        if info is None:
            raise ValueError(f"Unknown {plugin_type} detector plugin: {plugin_name!r}")
        dim = plugin_type[3:]           # 'DAQ0D' → '0D', 'DAQ1D' → '1D', etc.
        cls_name = f'DAQ_{dim}Viewer_{plugin_name}'

    module = info['module']
    return getattr(module, cls_name)


# ── Worker ─────────────────────────────────────────────────────────────────────

class ActorWorker(QObject):
    """Runs hardware init and actor lifecycle in a dedicated QThread.

    All public slots are invoked cross-thread via signals defined on
    :class:`PymodaqActorGUI`.

    ThreadCommand values emitted on ``status_sig``
    -----------------------------------------------
    ``'INSTRUMENT_INIT'``   attribute = initialised plugin instance
    ``'ACTOR_READY'``       attribute = :class:`Capabilities`
    ``'ACTOR_STOPPED'``     attribute = None
    ``'UPDATE_STATUS'``     attribute = str
    ``'ERROR'``             attribute = str
    """

    status_sig = Signal(ThreadCommand)

    def __init__(self):
        super().__init__()
        self._plugin_class = None          # set by init_instrument; used by start_actor
        self._actor: Optional[PymodaqActor] = None
        self._stop_event: Optional[threading.Event] = None
        self._actor_thread: Optional[threading.Thread] = None

    # ── Slots (called from the GUI thread via cross-thread signals) ────────────

    @Slot(object)
    def init_instrument(self, plugin_class):
        """Record the plugin class as ready.

        Hardware initialisation happens later in ``actor.connect()`` (Phase 2).
        ``ini_stage`` / ``ini_detector`` are **not** called here — those belong to the
        director side (DAQ_Move / DAQ_Viewer) when it connects to the running actor.

        Emits ``INSTRUMENT_INIT`` on success, ``ERROR`` on failure.
        """
        try:
            # Validate the class is callable (basic sanity check only)
            if not callable(plugin_class):
                raise TypeError(f'{plugin_class!r} is not callable')
        except Exception as exc:
            self.status_sig.emit(ThreadCommand('ERROR', f'Plugin class invalid: {exc}'))
            return

        self._plugin_class = plugin_class
        self.status_sig.emit(ThreadCommand('INSTRUMENT_INIT', plugin_class))

    @Slot(str, str, int)
    def start_actor(self, actor_name: str, host: str, port: int):
        """Phase 2: pass the plugin class to PymodaqActor and start listening.

        pyleco's Actor calls ``device_class()`` internally in ``connect()``,
        which runs ``plugin_class.__init__`` and opens the hardware connection
        through the plugin's own ``read()`` / ``write()`` lifecycle.
        """
        if self._plugin_class is None:
            self.status_sig.emit(ThreadCommand(
                'ERROR', 'No plugin loaded — run Init Instrument first'
            ))
            return

        try:
            self._actor = PymodaqActor(
                name=actor_name,
                device_class=self._plugin_class,
                host=host,
                port=port,
            )
            self._actor.connect()
        except Exception as exc:
            self.status_sig.emit(ThreadCommand('ERROR', f'Actor connection failed: {exc}'))
            return

        self._stop_event = threading.Event()
        self._actor_thread = threading.Thread(
            target=self._actor.listen,
            kwargs={'stop_event': self._stop_event},
            daemon=True,
            name=f'actor-listen-{actor_name}',
        )
        self._actor_thread.start()

        try:
            caps = Capabilities.from_dict(self._actor.get_capabilities())
        except Exception as exc:
            caps = Capabilities()
            logger.warning('Could not fetch capabilities: %s', exc)

        self.status_sig.emit(ThreadCommand('ACTOR_READY', caps))

    @Slot()
    def stop_actor(self):
        """Signal the actor's listen loop to exit, then disconnect."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._actor_thread is not None:
            self._actor_thread.join(timeout=3.0)
            self._actor_thread = None
        if self._actor is not None:
            try:
                self._actor.disconnect()
            except Exception:
                pass
            self._actor = None
        self._stop_event = None
        self.status_sig.emit(ThreadCommand('ACTOR_STOPPED'))

    @Slot()
    def close_instrument(self):
        """Clear the stored plugin class reference."""
        self._plugin_class = None
        self.status_sig.emit(ThreadCommand('UPDATE_STATUS', 'Instrument closed'))


# ── Main GUI ───────────────────────────────────────────────────────────────────

class PymodaqActorGUI(CustomApp):
    """Hardware-side GUI that wraps a plugin in a :class:`PymodaqActor`.

    Typical workflow
    ----------------
    1. Select *Plugin type* and *Plugin name*.
    2. Configure plugin settings in the Settings dock (optional).
    3. **Init Instrument** — hardware connects; Instrument LED → green.
    4. **Start Actor** — LECO actor starts; Coordinator + Actor LEDs → green;
       Capabilities dock appears.
    5. Click capability action buttons to open director windows.
    6. **Stop Actor** — shuts down the LECO side; LEDs → red.
    """

    # Cross-thread signals that drive the worker
    sig_init = Signal(object)            # plugin_class
    sig_start = Signal(str, str, int)    # actor_name, host, port
    sig_stop = Signal()
    sig_close_hw = Signal()

    params = [
        {'title': 'Actor name:', 'name': 'actor_name', 'type': 'str', 'value': 'actor'},
        {'title': 'Host:', 'name': 'host', 'type': 'str', 'value': 'localhost'},
        {'title': 'Port:', 'name': 'port', 'type': 'int', 'value': COORDINATOR_PORT},
        {'title': 'Plugin type:', 'name': 'plugin_type', 'type': 'list',
         'limits': ['Actuator', 'DAQ0D', 'DAQ1D', 'DAQ2D']},
        {'title': 'Plugin name:', 'name': 'plugin_name', 'type': 'list', 'limits': []},
        {'title': 'Auto-open directors:', 'name': 'auto_open_all', 'type': 'bool',
         'value': False,
         'tip': 'Open a director window for every capability when the actor starts'},
    ]

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent, title='PymodaqActor GUI', **kwargs)

        # Worker + thread
        self.worker = ActorWorker()
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.start()

        # GUI state
        self._plugin_class = None          # class selected in the list
        self._display_plugin = None        # temporary instance for settings display
        self._last_caps: Optional[Capabilities] = None
        self._open_directors: dict = {}    # key → SharedUI

        # LED widgets — created in setup_docks
        self.led_instrument: Optional[QLED] = None
        self.led_coordinator: Optional[QLED] = None
        self.led_actor: Optional[QLED] = None

        # Extra ParameterTrees (the main params live in self.settings_tree)
        self._plugin_settings_tree = ParameterTree()
        self._caps_tree = ParameterTree()

        self.setup_ui()
        self._update_plugin_name_limits()

    # ── CustomApp interface ────────────────────────────────────────────────────

    def setup_docks(self):
        """LECO dock (params + LEDs) / Settings dock / Capabilities dock."""
        # ── LECO dock ──────────────────────────────────────────────────────────
        self.docks['leco'] = Dock('LECO Actor', size=(420, 320))
        self.dockarea.addDock(self.docks['leco'])

        leco_widget = QtWidgets.QWidget()
        leco_layout = QtWidgets.QVBoxLayout(leco_widget)
        leco_layout.setContentsMargins(4, 4, 4, 4)
        leco_layout.addWidget(self.settings_tree)

        # LED panel
        led_panel = QtWidgets.QWidget()
        led_layout = QtWidgets.QHBoxLayout(led_panel)
        led_layout.setContentsMargins(4, 2, 4, 2)
        for label_text, attr in [
            ('Instrument', 'led_instrument'),
            ('Coordinator', 'led_coordinator'),
            ('Actor',       'led_actor'),
        ]:
            led = QLED(readonly=True)
            setattr(self, attr, led)
            led_layout.addWidget(QtWidgets.QLabel(label_text))
            led_layout.addWidget(led)
            led_layout.addSpacing(8)
        led_layout.addStretch()
        leco_layout.addWidget(led_panel)
        self.docks['leco'].addWidget(leco_widget)

        # ── Settings dock ──────────────────────────────────────────────────────
        self.docks['settings'] = Dock('Plugin Settings', size=(420, 280))
        self.dockarea.addDock(self.docks['settings'], 'bottom', self.docks['leco'])
        self.docks['settings'].addWidget(self._plugin_settings_tree)

        # ── Capabilities dock (hidden until ACTOR_READY) ───────────────────────
        self.docks['capabilities'] = Dock('Capabilities', size=(420, 300))
        self.dockarea.addDock(self.docks['capabilities'], 'right', self.docks['leco'])
        self.docks['capabilities'].addWidget(self._caps_tree)
        self.docks['capabilities'].hide()

    def setup_actions(self):
        """Init / Start / Stop toolbar buttons."""
        self.add_action('init',  'Init Instrument', icon_name='',
                        tip='Instantiate plugin and open hardware connection', enabled=True)
        self.add_action('start', 'Start Actor',     icon_name='',
                        tip='Start the LECO actor', enabled=False)
        self.add_action('stop',  'Stop Actor',      icon_name='',
                        tip='Stop the LECO actor', enabled=False)

    def connect_things(self):
        """Wire toolbar buttons ↔ worker signals ↔ status updates."""
        self.get_action('init').connect_to(self._on_init_clicked)
        self.get_action('start').connect_to(self._on_start_clicked)
        self.get_action('stop').connect_to(lambda: self.sig_stop.emit())

        # GUI → worker (queued cross-thread)
        self.sig_init.connect(self.worker.init_instrument)
        self.sig_start.connect(self.worker.start_actor)
        self.sig_stop.connect(self.worker.stop_actor)
        self.sig_close_hw.connect(self.worker.close_instrument)

        # Worker → GUI (queued, delivered in the main thread)
        self.worker.status_sig.connect(self._on_status)

    # ── Parameter changes ──────────────────────────────────────────────────────

    def value_changed(self, param):
        if param.name() == 'plugin_type':
            self._update_plugin_name_limits()
        elif param.name() == 'plugin_name':
            self._load_plugin_for_display()

    # ── Toolbar handlers ───────────────────────────────────────────────────────

    def _on_init_clicked(self):
        if self._plugin_class is None:
            self.statusbar.showMessage('Select a plugin first')
            return
        self.sig_init.emit(self._plugin_class)

    def _on_start_clicked(self):
        self.sig_start.emit(
            self.settings['actor_name'],
            self.settings['host'],
            int(self.settings['port']),
        )

    # ── Worker status dispatcher ───────────────────────────────────────────────

    def _on_status(self, cmd: ThreadCommand):
        command = cmd.command
        attr = cmd.attribute

        if command == 'INSTRUMENT_INIT':
            # attr is the plugin class; settings display was already done by
            # _load_plugin_for_display when the user selected the plugin name.
            self.led_instrument.set_as(True)
            self.get_action('init').setEnabled(True)
            self.get_action('start').setEnabled(True)
            self.get_action('stop').setEnabled(False)
            self.statusbar.showMessage('Instrument ready — click Start Actor to connect')

        elif command == 'ACTOR_READY':
            caps: Capabilities = attr
            self._last_caps = caps
            self.led_coordinator.set_as(True)
            self.led_actor.set_as(True)
            self.get_action('init').setEnabled(False)
            self.get_action('start').setEnabled(False)
            self.get_action('stop').setEnabled(True)
            self._populate_caps_tree(caps)
            self.docks['capabilities'].show()
            if self.settings['auto_open_all']:
                self._open_all_directors(caps)
            self.statusbar.showMessage('Actor ready')

        elif command == 'ACTOR_STOPPED':
            self.led_coordinator.set_as(False)
            self.led_actor.set_as(False)
            self.get_action('init').setEnabled(True)
            self.get_action('start').setEnabled(True)
            self.get_action('stop').setEnabled(False)
            self.docks['capabilities'].hide()
            self._last_caps = None
            self.statusbar.showMessage('Actor stopped')

        elif command == 'UPDATE_STATUS':
            self.statusbar.showMessage(str(attr))

        elif command == 'ERROR':
            self.led_instrument.set_as(False)
            self.statusbar.showMessage(f'Error: {attr}')
            logger.error('ActorWorker error: %s', attr)

    # ── Plugin discovery ───────────────────────────────────────────────────────

    def _update_plugin_name_limits(self):
        """Repopulate the *plugin_name* list when *plugin_type* changes."""
        ptype = self.settings['plugin_type']
        if ptype == 'Actuator':
            names = list(ACTUATOR_NAMES)
        else:
            names = [d['name'] for d in DET_TYPES.get(ptype, [])]

        name_param = self.settings.child('plugin_name')
        name_param.setLimits(names)
        if names:
            name_param.setValue(names[0])
            self._load_plugin_for_display()
        else:
            self._plugin_class = None
            self._display_plugin = None

    def _load_plugin_for_display(self):
        """Instantiate the plugin (no hardware) to display its settings tree."""
        plugin_type = self.settings['plugin_type']
        plugin_name = self.settings['plugin_name']
        if not plugin_name:
            return
        try:
            cls = _load_plugin_class(plugin_type, plugin_name)
            self._plugin_class = cls
            plugin = cls(parent=None)
            self._display_plugin = plugin
            self._plugin_settings_tree.setParameters(plugin.settings, showTop=False)
        except Exception as exc:
            logger.warning('Could not load plugin %s/%s: %s', plugin_type, plugin_name, exc)
            self._plugin_class = None
            self._display_plugin = None

    # ── Capabilities tree ──────────────────────────────────────────────────────

    def _populate_caps_tree(self, caps: Capabilities):
        """Build the capabilities ParameterTree from *caps*."""
        var_children = []
        for var in caps.variables:
            children = [
                {'name': 'units', 'type': 'str', 'value': var.units or '—', 'readonly': True},
                {'name': 'shape', 'type': 'str', 'value': str(var.shape), 'readonly': True},
            ]
            if isinstance(var, ContinuousVariable):
                children += [
                    {'name': 'range', 'type': 'str',
                     'value': f'[{var.lo}, {var.hi}]', 'readonly': True},
                    {'name': 'epsilon', 'type': 'float',
                     'value': var.epsilon, 'readonly': True},
                ]
            elif isinstance(var, DiscreteVariable):
                children.append(
                    {'name': 'choices', 'type': 'str',
                     'value': str(var.choices), 'readonly': True}
                )
            children.append({'name': 'Open DAQ_Move', 'type': 'action'})
            var_children.append({'name': var.name, 'type': 'group', 'children': children})

        obs_children = []
        for obs in caps.observables:
            children = [
                {'name': 'units', 'type': 'str', 'value': obs.units or '—', 'readonly': True},
                {'name': 'shape', 'type': 'str', 'value': str(obs.shape), 'readonly': True},
                {'name': 'dtype', 'type': 'str', 'value': obs.dtype, 'readonly': True},
                {'name': 'Open DAQ_Viewer', 'type': 'action'},
            ]
            obs_children.append({'name': obs.name, 'type': 'group', 'children': children})

        root = Parameter.create(name='Capabilities', type='group', children=[
            {'name': 'Variables',   'type': 'group', 'children': var_children},
            {'name': 'Observables', 'type': 'group', 'children': obs_children},
        ])

        for var in caps.variables:
            root.child('Variables', var.name, 'Open DAQ_Move').sigActivated.connect(
                lambda _p, n=var.name: self._open_director_for(n, 'variable')
            )
        for obs in caps.observables:
            root.child('Observables', obs.name, 'Open DAQ_Viewer').sigActivated.connect(
                lambda _p, n=obs.name: self._open_director_for(n, 'observable')
            )

        self._caps_tree.setParameters(root, showTop=False)

    def _open_all_directors(self, caps: Capabilities):
        for var in caps.variables:
            self._open_director_for(var.name, 'variable')
        for obs in caps.observables:
            self._open_director_for(obs.name, 'observable')

    def _open_director_for(self, cap_name: str, cap_type: str):
        """Open (or raise) a director window for *cap_name*."""
        key = f'{cap_type}:{cap_name}'
        existing = self._open_directors.get(key)
        if existing is not None:
            try:
                existing.show()
                existing.raise_()
                return
            except Exception:
                pass  # window was closed; fall through and recreate

        actor_name = self.settings['actor_name']
        host = self.settings['host']

        try:
            from pymodaq.utils.gui_utils.loader_utils import (
                create_load_daq_move, create_load_daq_viewer,
            )

            if cap_type == 'variable':
                shared_ui, daq_move = create_load_daq_move('Simple')
                daq_move.actuator = 'LECODirector'
                # leco_parameters are appended to params at class level.
                # They land under 'move_settings' in DAQ_Move_LECODirector.
                # TODO: confirm exact child path once live; update if needed.
                try:
                    daq_move.settings.child('move_settings', 'actor_name').setValue(actor_name)
                    daq_move.settings.child('move_settings', 'host').setValue(host)
                    daq_move.settings.child('move_settings', 'use_legacy_actor').setValue(False)
                except Exception:
                    logger.warning('Could not pre-fill move director settings for %s', cap_name)

            else:
                # Infer detector dimension from stored capabilities
                ndim = 1
                if self._last_caps is not None:
                    obs = next(
                        (o for o in self._last_caps.observables if o.name == cap_name), None
                    )
                    if obs is not None:
                        ndim = len(obs.shape)

                from pymodaq.control_modules.daq_viewer_ui.viewer_selector import SelectedModule
                from pymodaq.control_modules.instruments import DAQTypesEnum
                det_type = {1: 'DAQ0D', 2: 'DAQ1D', 3: 'DAQ2D'}.get(ndim, 'DAQ0D')
                shared_ui, daq_viewer = create_load_daq_viewer()
                daq_viewer.detector = SelectedModule(DAQTypesEnum[det_type], 'LECODirector')
                try:
                    daq_viewer.settings.child('detector_settings', 'actor_name').setValue(actor_name)
                    daq_viewer.settings.child('detector_settings', 'host').setValue(host)
                    daq_viewer.settings.child('detector_settings', 'use_legacy_actor').setValue(False)
                except Exception:
                    logger.warning('Could not pre-fill viewer director settings for %s', cap_name)

            self._open_directors[key] = shared_ui
            shared_ui.show()

        except Exception as exc:
            logger.error('Failed to open director for %s: %s', cap_name, exc)
            self.statusbar.showMessage(f'Could not open director: {exc}')

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Stop actor + hardware, close all directors, shut down worker thread."""
        # Stop actor and hardware in worker thread (blocking so cleanup completes)
        QMetaObject.invokeMethod(
            self.worker, 'stop_actor',
            Qt.ConnectionType.BlockingQueuedConnection,
        )
        QMetaObject.invokeMethod(
            self.worker, 'close_instrument',
            Qt.ConnectionType.BlockingQueuedConnection,
        )

        for shared_ui in list(self._open_directors.values()):
            try:
                shared_ui.close()
            except Exception:
                pass
        self._open_directors.clear()

        self.worker_thread.quit()
        self.worker_thread.wait()

        event.accept()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    """Launch the PymodaqActor GUI (entry point: ``pymodaq-actor-gui``)."""
    import sys
    app = mkQApp('PymodaqActor GUI')
    from pymodaq.utils.gui_utils.widgets.window import make_window
    win, area = make_window(title='PymodaqActor GUI')
    gui = PymodaqActorGUI(area)
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
