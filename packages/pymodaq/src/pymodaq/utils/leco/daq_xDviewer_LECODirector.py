from __future__ import annotations
from typing import Optional, Union

from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.control_modules.thread_commands import ThreadStatus, ThreadStatusViewer
from pymodaq.utils.data import DataFromPlugins, Axis
from pymodaq_data import DataToExport
from serializall import SerializableFactory
from pymodaq_utils.utils import ThreadCommand, getLineInfo

from pymodaq.utils import data  # for serialization factory registration  # noqa: F401
from pymodaq_gui.parameter import Parameter

from pymodaq.utils.leco.leco_director import LECODirector, leco_parameters
from pymodaq.utils.leco.director_utils import DetectorDirector, PymodaqDetectorDirector
from pymodaq_utils.logger import set_logger, get_module_name

import numpy as np

logger = set_logger(get_module_name(__file__))


class DAQ_xDViewer_LECODirector(LECODirector, DAQ_Viewer_base):
    """A control module, which in the dashboard, allows to control a remote Viewer module.

    This is the base class for the viewer LECO director modules.
    """

    settings: Parameter
    controller: Union[DetectorDirector, PymodaqDetectorDirector]

    params_GRABBER = []

    socket_types = ["GRABBER"]
    params = comon_parameters + leco_parameters + [
        {'title': 'Observable name:', 'name': 'observable_name', 'type': 'list',
         'limits': ['data'], 'value': 'data',
         'tip': 'Which observable (channel) this viewer shows. '
                'Populated automatically from actor capabilities on init or via "Query capabilities".'},
        {'title': 'Live acquisition mode:', 'name': 'live_mode', 'type': 'list',
         'limits': ['sequential', 'continuous'], 'value': 'sequential',
         'tip': (
             'sequential: director requests one frame at a time — inherently backpressure-safe, '
             'rate limited by device.read() + network round-trip. '
             'continuous: actor streams at max_rate_hz — lower overhead for fast sensors, '
             'but can overwhelm the GUI for large arrays if rate_hz is too high.'
         )},
        {'title': 'Max rate (Hz):', 'name': 'max_rate_hz', 'type': 'float', 'value': 10.0,
         'tip': 'Maximum publish rate used in continuous live mode. 0 = unlimited (not recommended for large arrays).'},
    ]
    live_mode_available = True

    def __init__(
        self,
        parent=None,
        params_state=None,
        grabber_type: str = "0D",
        host: Optional[str] = None,
        port: Optional[int] = None,
        **kwargs,
    ) -> None:
        DAQ_Viewer_base.__init__(self, parent=parent, params_state=params_state)
        if host is not None:
            self.settings["host"] = host
        if port is not None:
            self.settings["port"] = port
        LECODirector.__init__(self, host=self.settings["host"], port=self.settings["port"])

        self.register_binary_rpc_methods((self.set_data,))
        self.register_rpc_methods((self.on_grab_status,))

        self.client_type = "GRABBER"
        self.x_axis = None
        self.y_axis = None
        self.data = None
        self.grabber_type = grabber_type
        self.ind_data = 0
        self.data_mock = None
        self._live_sequential: bool = False  # True only during sequential live grab
        self.start_timer()
        # Connect ZMQ data-channel messages (new actor path) to local handler.
        # data_signal is dedicated to ZMQ frames so high-rate data never blocks
        # control commands (stop_grab etc.) queued on cmd_signal.
        self.listener.signals.data_signal.connect(self._on_actor_data)

    def ini_detector(self, controller=None):
        """
            | Initialisation procedure of the detector updating the status dictionary.
            |
            | Init axes from image , here returns only None values (to tricky to di it with the
              server and not really necessary for images anyway)

            See Also
            --------
            utility_classes.DAQ_TCP_server.init_server, get_xaxis, get_yaxis
        """

        actor_name = self.settings["actor_name"]
        if self.is_master:
            if self.settings['use_legacy_actor']:
                self.controller = DetectorDirector(actor=actor_name, communicator=self.communicator)
                try:
                    self.controller.set_remote_name(self.communicator.full_name)
                except TimeoutError:
                    logger.warning("Timeout setting remote name.")
                self.controller.get_settings()
            else:
                self.controller = PymodaqDetectorDirector(actor=actor_name, communicator=self.communicator)
                try:
                    caps = self.controller.get_capabilities()
                    obs_names = [o.name for o in caps.observables] or ['data']
                except Exception:
                    obs_names = ['data']
                    logger.warning("Could not fetch capabilities; defaulting observable name to 'data'.")
                # Populate the observable_name list with what this actor actually exposes.
                self._apply_observable_names(obs_names)
                try:
                    self.controller.subscribe_settings()
                except Exception:
                    logger.warning("Timeout during subscribe_settings.")
                # Subscribe to the per-channel sub-topic: "{namespace.actor}/{obs_name}".
                # The actor publishes each DWA to its own sub-topic so ZMQ drops
                # frames for other channels before they reach Python.
                _namespace = self.communicator.namespace
                self._actor_full_name = f"{_namespace}.{actor_name}" if _namespace else actor_name
                obs_name = self.settings['observable_name'] or 'data'
                self._actor_sub_name = f"{self._actor_full_name}/{obs_name}"
                try:
                    self.listener.subscribe(self._actor_sub_name)
                except Exception:
                    logger.warning("Could not subscribe to actor ZMQ data channel.")
                # Request initial frame so the display is populated on startup.
                try:
                    obs_name = self.settings['observable_name'] or None
                    self.controller.query_data(names=[obs_name] if obs_name else None, fresh=True)
                except Exception:
                    logger.warning("Could not request initial data from actor.")
        else:
            self.controller = controller

        initialized = True
        info = 'Viewer Director ready'
        return info, initialized

    def grab_data(self, Naverage=1, **kwargs):
        """
            Start new acquisition.
            Grabbed indice is used to keep track of the current image in the average.

            ============== ========== ==============================
            **Parameters**   **Type**  **Description**

            *Naverage*        int       Number of images to average
            ============== ========== ==============================

            See Also
            --------
            utility_classes.DAQ_TCP_server.process_cmds
        """

        self.ind_grabbed = 0  # to keep track of the current image in the average
        self.Naverage = Naverage
        if self.settings['use_legacy_actor']:
            if kwargs.get('live', False):
                self.controller.send_data_grab()
            else:
                self.controller.send_data_snap()
        else:
            obs_name = self.settings['observable_name'] or None
            obs_names = [obs_name] if obs_name else None
            if kwargs.get('live', False):
                if self.settings['live_mode'] == 'continuous':
                    # Actor background thread streams frames at the configured rate.
                    # Director receives passively via ZMQ subscription.
                    rate_hz = self.settings['max_rate_hz']
                    self.controller.query_data_continuous(rate_hz=rate_hz)
                else:
                    # Sequential: request one frame; _on_actor_data re-requests the next.
                    # Naturally backpressure-safe — rate bounded by device.read() latency.
                    self._live_sequential = True
                    self.controller.query_data(names=obs_names, fresh=True)
            else:
                # Single snap: actor reads once and publishes one ZMQ frame.
                self._live_sequential = False
                self.controller.query_data(names=obs_names, fresh=True)

    def stop(self):
        """Stop grabbing."""
        self._live_sequential = False          # halt sequential loop regardless of mode
        if self.settings['use_legacy_actor']:
            self.controller.stop_grab()
        else:
            if self.settings['live_mode'] == 'continuous':
                try:
                    self.controller.stop_continuous()
                except Exception:
                    logger.warning("stop: could not stop actor continuous grab")

    def _on_actor_data(self, topic: str, dte) -> None:
        """Handle data published by the PymodaqActor on the ZMQ data channel.

        The director is subscribed to ``"{actor}/{observable_name}"`` so only
        frames for this channel arrive here — no name filtering needed.
        Called when ``use_legacy_actor=False``.
        """
        if dte is None:
            return
        self.dte_signal.emit(dte)
        if self._live_sequential:
            # Sequential mode: request next frame only after this one was received.
            # Provides automatic backpressure — no frame is requested before the
            # previous DataToExport has been delivered to the viewer.
            obs_name = self.settings['observable_name'] or None
            try:
                self.controller.query_data(
                    names=[obs_name] if obs_name else None, fresh=True
                )
            except Exception:
                logger.warning("_on_actor_data: failed to request next frame; stopping sequential grab")
                self._live_sequential = False

    def set_data(self, data: Union[dict,list, str, float, None],
                 additional_payload: Optional[list[bytes]] = None) -> None:
        """
        Set the grabbed data signal.

        corresponds to the "data_ready" signal

        :param data: If None, look for the additional object
        """
        if additional_payload:
            dte = SerializableFactory().get_apply_deserializer(additional_payload[0])
        elif data is not None:
            axes = []
            labels = []
            multichannel = False
            if isinstance(data, dict):
                axes = [
                    Axis( label=axis.get('label', ''),
                          units=axis.get('units', ''),
                          data=np.array(axis.get('data', [])),
                          index=ind
                    ) for ind, axis in enumerate(data.get('axes', []))
                ]
                labels = data.get('labels', [])
                multichannel = data.get('multichannel', False)
                data = data.get('data', [])
            if multichannel:
                # data[0] may fail if data is empty, but it shouldn't happen
                ndim = np.array(data[0]).ndim
                data = [np.atleast_1d(d) for d in data]
            else:
                ndim = np.array(data).ndim
                data = [np.atleast_1d(data)]

            dfp = DataFromPlugins(self.controller.actor, data=data, axes=axes[:ndim], labels=labels)
            dte = DataToExport('Copy', data=[dfp])
        else:
            raise ValueError("Can't set_data when data is None")
        self.dte_signal.emit(dte)

    # ── Capability refresh ─────────────────────────────────────────────────────

    def commit_settings(self, param) -> None:
        super().commit_settings(param)
        if param.name() == 'observable_name' and getattr(self, '_actor_full_name', None):
            new_obs = param.value() or 'data'
            new_topic = f"{self._actor_full_name}/{new_obs}"
            if new_topic != self._actor_sub_name:
                try:
                    self.listener.unsubscribe(self._actor_sub_name)
                    self.listener.subscribe(new_topic)
                    self._actor_sub_name = new_topic
                except Exception:
                    logger.warning("Could not update ZMQ subscription for observable change.")
        elif param.name() == 'query_caps':
            self._query_and_apply_capabilities()

    def _query_and_apply_capabilities(self) -> None:
        """Ask the actor for its capabilities and update the observable_name selector."""
        if self.settings['use_legacy_actor']:
            logger.info("Capability query only supported with use_legacy_actor=False.")
            return
        actor_name = self.settings['actor_name']
        try:
            tmp = PymodaqDetectorDirector(actor=actor_name, communicator=self.communicator)
            caps = tmp.get_capabilities()
            obs_names = [o.name for o in caps.observables] or ['data']
            self._apply_observable_names(obs_names)
            logger.info("Capabilities refreshed from actor '%s': observables=%s", actor_name, obs_names)
        except Exception as exc:
            logger.warning("Could not query capabilities from actor '%s': %s", actor_name, exc)

    def _apply_observable_names(self, obs_names: list) -> None:
        current = self.settings['observable_name']
        self.settings.child('observable_name').setLimits(obs_names)
        if current not in obs_names:
            self.settings.child('observable_name').setValue(obs_names[0])

    def on_grab_status(self, grabbed_names, is_continuous: bool) -> None:
        """Invoked by the actor when its continuous-grab status changes.

        Allows this director's GUI to mirror the grab state of the actor
        even when the grab was initiated by a different director.

        Parameters
        ----------
        grabbed_names:
            List of names currently being grabbed, or ``None`` for all.
        is_continuous:
            ``True`` while the actor's background grab loop is running.
        """
        if not is_continuous:
            # If actor stopped, also halt sequential loop on this director.
            self._live_sequential = False
        self.emit_status(ThreadCommand('GRAB_STATUS', {
            'grabbed_names': grabbed_names,
            'is_continuous': is_continuous,
        }))

    def close(self) -> None:
        self.timer.stop()
        if not self.settings['use_legacy_actor'] and self.controller is not None:
            try:
                self.controller.unsubscribe_settings()
            except Exception:
                pass
            try:
                self.listener.unsubscribe(getattr(self, '_actor_sub_name', self.settings['actor_name']))
            except Exception:
                pass
        super().close()

if __name__ == '__main__':
    main(__file__, init=False)
