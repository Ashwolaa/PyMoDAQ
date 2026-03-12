"""PymodaqActor GUI — hardware-side launcher for PymodaqActor.

Runs on the **acquisition computer** (hardware side).  Lets the user:

1. Select a hardware class from the ``pymodaq.hardware`` entry-point registry.
2. Preview the class's :class:`~pymodaq.control_modules.capabilities.Capabilities`
   in the Capabilities dock before starting.
3. Click **Init Instrument** — instantiates the device class, opens the hardware
   connection, registers with the LECO coordinator, and starts listening.
   This is the single initialisation step; it is equivalent to what
   ``ini_stage`` / ``ini_detector`` do on the director side, combined with
   starting the LECO actor.
4. Open :class:`DAQ_Move_LECODirector` / :class:`DAQ_xDViewer_LECODirector`
   windows for each capability the actor declares.
5. Click **Stop** — closes hardware, disconnects from coordinator.

Thread model
------------
Main thread (Qt)
└── PymodaqActorGUI  (CustomApp + ParameterManager)
    │  Owns all GUI state.  Drives the worker via cross-thread signals.
    └── QThread: worker_thread
        └── ActorWorker  (QObject)
            ├── init_instrument() — full startup: instantiate + connect + listen
            └── stop_actor()     — stop listen loop + disconnect
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from qtpy import QtWidgets
from qtpy.QtCore import QMetaObject, QObject, QThread, Signal, Slot, Qt

from pymodaq_gui.parameter import Parameter, ParameterTree
from pymodaq_gui.qt_utils import mkQApp  # used by main()
from pymodaq_gui.utils.custom_app import CustomApp
from pymodaq_gui.utils.dock import Dock
from pymodaq_gui.utils.widgets.qled import QLED
from pymodaq_utils.utils import ThreadCommand
from pyleco.core import COORDINATOR_PORT, PROXY_RECEIVING_PORT

from pymodaq.control_modules.capabilities import (
    Capabilities, ContinuousVariable, DiscreteVariable,
)
from pymodaq.utils.leco.actor import PymodaqActor
from pymodaq.utils.leco.hardware_registry import HARDWARE_REGISTRY, HARDWARE_NAMES

logger = logging.getLogger(__name__)


# ── Worker ─────────────────────────────────────────────────────────────────────

class ActorWorker(QObject):
    """Runs the actor lifecycle in a dedicated QThread.

    ThreadCommand values emitted on ``status_sig``
    -----------------------------------------------
    ``'ACTOR_READY'``     attribute = :class:`Capabilities`
    ``'ACTOR_STOPPED'``   attribute = None
    ``'UPDATE_STATUS'``   attribute = str
    ``'ERROR'``           attribute = str
    """

    status_sig = Signal(ThreadCommand)

    def __init__(self):
        super().__init__()
        self._actor: Optional[PymodaqActor] = None
        self._stop_event: Optional[threading.Event] = None
        self._actor_thread: Optional[threading.Thread] = None

    @Slot(object, str, str, int, str, int, object, object)
    def init_instrument(self, plugin_class, actor_name: str, host: str, port: int,
                        proxy_host: str = 'localhost',
                        proxy_port: int = PROXY_RECEIVING_PORT,
                        channel_proxies: Optional[dict] = None,
                        published_names: Optional[list] = None):
        """Full initialisation: instantiate device, connect hardware, start actor.

        Equivalent to ``ini_stage`` / ``ini_detector`` + LECO actor startup in
        one step.  ``plugin_class()`` is called here (hardware connection opens);
        the LECO actor then starts listening for director commands.

        Emits ``ACTOR_READY`` on success, ``ERROR`` on failure.
        """
        try:
            self._actor = PymodaqActor(
                name=actor_name,
                device_class=plugin_class,
                host=host,
                port=port,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                channel_proxies=channel_proxies or {},
                published_names=published_names,
            )
            self._actor.connect()
        except Exception as exc:
            self.status_sig.emit(ThreadCommand('ERROR', f'Init failed: {exc}'))
            self._actor = None
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
        """Stop the listen loop and disconnect from hardware + coordinator."""
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


# ── Main GUI ───────────────────────────────────────────────────────────────────

class PymodaqActorGUI(CustomApp):
    """Hardware-side GUI that wraps a plugin in a :class:`PymodaqActor`.

    Workflow
    --------
    1. Select an *Instrument* from the list; the Capabilities dock shows a
       preview of what will be exposed (no hardware touched yet).
    2. **Init Instrument** — opens hardware connection + starts LECO actor.
       All three LEDs turn green; Capabilities dock refreshes with live data.
    3. Click capability action buttons to open director windows.
    4. **Stop** — closes hardware, disconnects from coordinator.  LEDs grey;
       Capabilities dock reverts to preview.
    """

    sig_init = Signal(object, str, str, int, str, int, object, object)  # plugin_class, actor_name, host, port, proxy_host, proxy_port, channel_proxies, published_names
    sig_stop = Signal()

    params = [
        {'title': 'Actor name:', 'name': 'actor_name', 'type': 'str', 'value': 'actor'},
        {'title': 'Host:',       'name': 'host',       'type': 'str', 'value': 'localhost'},
        {'title': 'Port:',       'name': 'port',       'type': 'int', 'value': COORDINATOR_PORT},
        {'title': 'Instrument:', 'name': 'instrument',  'type': 'list',
         'limits': HARDWARE_NAMES},
        {'title': 'Auto-open directors:', 'name': 'auto_open_all', 'type': 'bool',
         'value': False,
         'tip': 'Open a director window for every capability when the actor starts'},
        {'title': 'Proxy host:', 'name': 'proxy_host', 'type': 'str', 'value': 'localhost',
         'tip': 'Default ZMQ data-channel proxy host (applies to all channels unless overridden)'},
        {'title': 'Proxy port:', 'name': 'proxy_port', 'type': 'int',
         'value': PROXY_RECEIVING_PORT,
         'tip': 'Default ZMQ data-channel proxy port (applies to all channels unless overridden)'},
    ]

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent, title='PymodaqActor GUI', **kwargs)

        self.worker = ActorWorker()
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.start()

        self._plugin_class = None
        self._last_caps: Optional[Capabilities] = None
        self._current_caps: Optional[Capabilities] = None
        self._caps_root = None
        self._open_directors: dict = {}

        self.led_instrument: Optional[QLED] = None
        self.led_coordinator: Optional[QLED] = None
        self.led_actor: Optional[QLED] = None

        self._caps_tree = ParameterTree()

        self.setup_ui()

        if HARDWARE_NAMES:
            self._on_instrument_selected()
        else:
            self.statusbar.showMessage(
                'No hardware classes registered — install a plugin package that '
                'uses pymodaq.hardware entry points.'
            )

    # ── CustomApp interface ────────────────────────────────────────────────────

    def setup_docks(self):
        self.docks['leco'] = Dock('LECO Actor', size=(420, 320))
        self.dockarea.addDock(self.docks['leco'])

        leco_widget = QtWidgets.QWidget()
        leco_layout = QtWidgets.QVBoxLayout(leco_widget)
        leco_layout.setContentsMargins(4, 4, 4, 4)
        leco_layout.addWidget(self.settings_tree)

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

        self.docks['capabilities'] = Dock('Capabilities', size=(420, 300))
        self.dockarea.addDock(self.docks['capabilities'], 'right', self.docks['leco'])
        self.docks['capabilities'].addWidget(self._caps_tree)
        self.docks['capabilities'].hide()

    def setup_actions(self):
        self.add_action('init', 'Init Instrument', icon_name='',
                        tip='Open hardware connection and start LECO actor',
                        enabled=True)
        self.add_action('stop', 'Stop', icon_name='',
                        tip='Stop actor and close hardware connection',
                        enabled=False)

    def connect_things(self):
        self.get_action('init').connect_to(self._on_init_clicked)
        self.get_action('stop').connect_to(lambda: self.sig_stop.emit())

        self.sig_init.connect(self.worker.init_instrument)
        self.sig_stop.connect(self.worker.stop_actor)

        self.worker.status_sig.connect(self._on_status)

    # ── Parameter changes ──────────────────────────────────────────────────────

    def value_changed(self, param):
        if param.name() == 'instrument':
            self._on_instrument_selected()

    # ── Toolbar handler ────────────────────────────────────────────────────────

    def _on_init_clicked(self):
        if self._plugin_class is None:
            self.statusbar.showMessage('Select an instrument first')
            return
        self.sig_init.emit(
            self._plugin_class,
            self.settings['actor_name'],
            self.settings['host'],
            int(self.settings['port']),
            self.settings['proxy_host'],
            int(self.settings['proxy_port']),
            self._collect_channel_proxies(),
            self._collect_published_names(),
        )

    def _collect_published_names(self) -> list:
        """Read per-channel Publish checkboxes from the capabilities tree.

        Returns a list of observable/variable names whose Publish checkbox is
        checked.  An empty list means no continuous publication (user must
        explicitly check at least one item).
        """
        names: list = []
        if self._caps_root is None or self._current_caps is None:
            return names
        for var in self._current_caps.variables:
            try:
                if self._caps_root.child('Variables', var.name, 'publish').value():
                    names.append(var.name)
            except Exception:
                pass
        for obs in self._current_caps.observables:
            try:
                if self._caps_root.child('Observables', obs.name, 'publish').value():
                    names.append(obs.name)
            except Exception:
                pass
        return names

    def _collect_channel_proxies(self) -> dict:
        """Read per-channel proxy overrides from the capabilities tree.

        Returns a dict mapping channel name → (host, port) only for channels
        whose proxy differs from the global ``proxy_host`` / ``proxy_port`` settings.
        """
        proxies: dict = {}
        if self._caps_root is None or self._current_caps is None:
            return proxies
        default_host = self.settings['proxy_host'] or 'localhost'
        default_port = int(self.settings['proxy_port'] or PROXY_RECEIVING_PORT)
        for var in self._current_caps.variables:
            try:
                ch_host = self._caps_root.child('Variables', var.name, 'Proxy', 'proxy_host').value()
                ch_port = int(self._caps_root.child('Variables', var.name, 'Proxy', 'proxy_port').value())
                if ch_host and (ch_host != default_host or ch_port != default_port):
                    proxies[var.name] = (ch_host, ch_port)
            except Exception:
                pass
        for obs in self._current_caps.observables:
            try:
                ch_host = self._caps_root.child('Observables', obs.name, 'Proxy', 'proxy_host').value()
                ch_port = int(self._caps_root.child('Observables', obs.name, 'Proxy', 'proxy_port').value())
                if ch_host and (ch_host != default_host or ch_port != default_port):
                    proxies[obs.name] = (ch_host, ch_port)
            except Exception:
                pass
        return proxies

    # ── Worker status dispatcher ───────────────────────────────────────────────

    def _on_status(self, cmd: ThreadCommand):
        command = cmd.command
        attr = cmd.attribute

        if command == 'ACTOR_READY':
            caps: Capabilities = attr
            self._last_caps = caps
            self.led_instrument.set_as(True)
            self.led_coordinator.set_as(True)
            self.led_actor.set_as(True)
            self.get_action('init').setEnabled(False)
            self.get_action('stop').setEnabled(True)
            self._populate_caps_tree(caps)
            self.docks['capabilities'].show()
            if self.settings['auto_open_all']:
                self._open_all_directors(caps)
            self.statusbar.showMessage('Actor ready')

        elif command == 'ACTOR_STOPPED':
            self.led_instrument.set_as(False)
            self.led_coordinator.set_as(False)
            self.led_actor.set_as(False)
            self.get_action('init').setEnabled(True)
            self.get_action('stop').setEnabled(False)
            self._last_caps = None
            self._on_instrument_selected()   # revert to preview
            self.statusbar.showMessage('Actor stopped')

        elif command == 'UPDATE_STATUS':
            self.statusbar.showMessage(str(attr))

        elif command == 'ERROR':
            self.led_instrument.set_as(False)
            self.led_coordinator.set_as(False)
            self.led_actor.set_as(False)
            self.get_action('init').setEnabled(True)
            self.get_action('stop').setEnabled(False)
            self.statusbar.showMessage(f'Error: {attr}')
            logger.error('ActorWorker error: %s', attr)

    # ── Instrument selection ───────────────────────────────────────────────────

    def _on_instrument_selected(self):
        """Load class + preview capabilities when the user selects an instrument."""
        name = self.settings['instrument']
        entry = next((e for e in HARDWARE_REGISTRY if e['name'] == name), None)
        if entry is None:
            self._plugin_class = None
            self.docks['capabilities'].hide()
            return
        self._plugin_class = entry['cls']
        self._populate_caps_tree(entry['capabilities'])
        self.docks['capabilities'].show()

    # ── Capabilities tree ──────────────────────────────────────────────────────

    def _populate_caps_tree(self, caps: Capabilities):
        default_proxy_host = self.settings['proxy_host'] or 'localhost'
        default_proxy_port = int(self.settings['proxy_port'] or PROXY_RECEIVING_PORT)

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
            children += [
                {'name': 'publish', 'type': 'bool', 'value': False,
                 'tip': 'Include this variable in continuous publication'},
                {'name': 'Open DAQ_Move', 'type': 'action'},
                {'name': 'Proxy', 'type': 'group', 'children': [
                    {'name': 'proxy_host', 'type': 'str', 'value': default_proxy_host,
                     'tip': 'ZMQ proxy host for this channel'},
                    {'name': 'proxy_port', 'type': 'int', 'value': default_proxy_port,
                     'tip': 'ZMQ proxy port for this channel'},
                ]},
            ]
            var_children.append({'name': var.name, 'type': 'group', 'children': children})

        obs_children = []
        for obs in caps.observables:
            children = [
                {'name': 'units', 'type': 'str', 'value': obs.units or '—', 'readonly': True},
                {'name': 'shape', 'type': 'str', 'value': str(obs.shape), 'readonly': True},
                {'name': 'dtype', 'type': 'str', 'value': obs.dtype, 'readonly': True},
                {'name': 'publish', 'type': 'bool', 'value': False,
                 'tip': 'Include this observable in continuous publication'},
                {'name': 'Open DAQ_Viewer', 'type': 'action'},
                {'name': 'Proxy', 'type': 'group', 'children': [
                    {'name': 'proxy_host', 'type': 'str', 'value': default_proxy_host,
                     'tip': 'ZMQ proxy host for this channel'},
                    {'name': 'proxy_port', 'type': 'int', 'value': default_proxy_port,
                     'tip': 'ZMQ proxy port for this channel'},
                ]},
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

        self._caps_root = root
        self._current_caps = caps
        self._caps_tree.setParameters(root, showTop=False)

    def _open_all_directors(self, caps: Capabilities):
        for var in caps.variables:
            self._open_director_for(var.name, 'variable')
        for obs in caps.observables:
            self._open_director_for(obs.name, 'observable')

    def _open_director_for(self, cap_name: str, cap_type: str):
        key = f'{cap_type}:{cap_name}'
        existing = self._open_directors.get(key)
        if existing is not None:
            try:
                existing.show()
                existing.raise_()
                return
            except Exception:
                pass

        actor_name = self.settings['actor_name']
        host = self.settings['host']

        try:
            from pymodaq.utils.gui_utils.loader_utils import (
                create_load_daq_move, create_load_daq_viewer,
            )

            if cap_type == 'variable':
                shared_ui, daq_move = create_load_daq_move('Simple')
                daq_move.actuator = 'LECODirector'
                try:
                    daq_move.settings.child('move_settings', 'actor_name').setValue(actor_name)
                    daq_move.settings.child('move_settings', 'host').setValue(host)
                    daq_move.settings.child('move_settings', 'use_legacy_actor').setValue(False)
                    daq_move.settings.child('move_settings', 'variable_name').setValue(cap_name)
                except Exception:
                    logger.warning('Could not pre-fill move director settings for %s', cap_name)

            else:
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
                    daq_viewer.settings.child('detector_settings', 'observable_name').setValue(cap_name)
                except Exception:
                    logger.warning('Could not pre-fill viewer director settings for %s', cap_name)

            self._open_directors[key] = shared_ui
            shared_ui.show()

        except Exception as exc:
            logger.error('Failed to open director for %s: %s', cap_name, exc)
            self.statusbar.showMessage(f'Could not open director: {exc}')

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        QMetaObject.invokeMethod(
            self.worker, 'stop_actor',
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
    from pymodaq.utils.gui_utils.loader_utils import create_load_actor_gui
    shared_ui, _ = create_load_actor_gui()
    shared_ui.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
