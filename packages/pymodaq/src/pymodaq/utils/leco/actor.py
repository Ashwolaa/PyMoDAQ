"""PymodaqActor — headless hardware process for PyMoDAQ.

Wraps :class:`pyleco.actors.Actor` and exposes a unified hardware interface over LECO:

    ``query_data(names, fresh)``   — read observables / variables
    ``change_to(name, value)``     — write a variable

Legacy RPC method names (``grab``, ``snap``, ``move_abs``, …) are registered as aliases
so that existing :class:`DAQ_Move_LECODirector` / :class:`DAQ_xDViewer_LECODirector`
plugins continue to work without changes during the Phase 1 → Phase 2 transition.

**Device interface** — the object passed as ``device_class`` must implement::

    device.connect()                                          — open hardware
    device.close()                                            — close hardware
    device.read(names: list[str] | None = None) -> DataToExport
    device.write(name: str, value: Any) -> None

``connect()`` is called by :meth:`PymodaqActor.connect` immediately after
``device_class()`` is instantiated.  ``close()`` is called by
:meth:`PymodaqActor.disconnect` instead of pyleco's default
``device.adapter.close()`` (which assumes a pymeasure instrument).

and may optionally implement::

    device.capabilities  -> Capabilities  (else infer_capabilities(device) is used)
    device.get_settings() -> str          (XML parameter tree)
    device.set_info(path: str, value)     (update a parameter)
    device.move_rel(delta: float)         (relative move)
    device.home()                         (move to home position)

No Qt import in this module.  Device objects that are full ``DAQ_Move_base`` /
``DAQ_Viewer_base`` subclasses will bring Qt in via the device class itself; for
headless testing a pure-Python mock device is sufficient.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from pyleco.actors.actor import Actor
from pyleco.core import PROXY_RECEIVING_PORT
from pyleco.core.serialization import generate_conversation_id
from pyleco.utils.data_publisher import DataPublisher

from pymodaq_data import DataToExport

from pymodaq.control_modules.capabilities import Capabilities, infer_capabilities

logger = logging.getLogger(__name__)


class PymodaqActor(Actor):
    """Hardware actor for PyMoDAQ.

    Parameters
    ----------
    name:
        LECO actor name (used as ZMQ topic for data-channel publications).
    device_class:
        Class of the hardware plugin.  Instantiated by :meth:`connect`.
    periodic_reading:
        Interval in seconds for the periodic readout timer (−1 = disabled).
    **kwargs:
        Forwarded to :class:`pyleco.actors.Actor` (``host``, ``port``, ``context``, …).
    """

    _director_registry: set[str]
    _last_data: Optional[Any]   # DataToExport or None
    _stop_grab_flag: bool

    def __init__(
        self,
        name: str,
        device_class,
        periodic_reading: float = -1,
        proxy_host: str = 'localhost',
        proxy_port: int = PROXY_RECEIVING_PORT,
        channel_proxies: Optional[dict] = None,
        published_names: Optional[list] = None,
        **kwargs,
    ) -> None:
        context = kwargs.get('context')
        super().__init__(name=name, device_class=device_class,
                         periodic_reading=periodic_reading, **kwargs)
        # Always recreate the publisher so we can honour proxy_host/proxy_port.
        # (super().__init__ creates a default publisher on localhost:11100.)
        self.publisher.close()
        self.publisher = DataPublisher(
            full_name=name,
            host=proxy_host,
            port=proxy_port,
            context=context,
        )
        # Per-channel publisher routing.
        # Maps channel_name → (host, port) key used in _extra_publishers.
        self._channel_proxy_keys: dict[str, tuple[str, int]] = {}
        # Maps (host, port) → DataPublisher for channels that use a different proxy.
        self._extra_publishers: dict[tuple[str, int], DataPublisher] = {}
        if channel_proxies:
            for ch_name, (ch_host, ch_port) in channel_proxies.items():
                key: tuple[str, int] = (ch_host, ch_port)
                if key not in self._extra_publishers:
                    self._extra_publishers[key] = DataPublisher(
                        full_name=name,
                        host=ch_host,
                        port=ch_port,
                        context=context,
                    )
                self._channel_proxy_keys[ch_name] = key
        self._director_registry: set[str] = set()
        self._last_data = None
        self._stop_grab_flag = False
        self._grab_thread: Optional[threading.Thread] = None
        self._published_names: Optional[set[str]] = set(published_names) if published_names is not None else None
        self._grabbed_names: Optional[set[str]] = None

    # ── Hardware lifecycle ─────────────────────────────────────────────────────

    def connect(self, *args, **kwargs) -> None:
        """Instantiate the device class then call ``device.connect()`` to open hardware.

        pyleco's base :meth:`Actor.connect` only runs ``device = device_class(*args, **kwargs)``.
        We follow up with an explicit ``device.connect()`` so that PyMoDAQ plugins (which
        separate construction from hardware open) behave correctly.
        """
        super().connect(*args, **kwargs)   # sets self.device = device_class(...)
        self.device.connect()

    def disconnect(self) -> None:
        """Call ``device.close()`` then clean up.

        Overrides pyleco's default which assumes a pymeasure instrument
        (``device.adapter.close()``).  PyMoDAQ plugins use ``close()`` instead.
        """
        self.stop_timer()
        for pub in list(self._extra_publishers.values()):
            try:
                pub.close()
            except Exception:
                pass
        self._extra_publishers.clear()
        self._channel_proxy_keys.clear()
        try:
            self.device.close()
        except AttributeError:
            logger.warning("Device has no close() method; skipping hardware disconnect.")
        except Exception:
            logger.exception("disconnect: device.close() raised an exception")
        try:
            del self.device
        except AttributeError:
            pass

    # ── RPC method registration ────────────────────────────────────────────────

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()

        # Primary interface
        self.register_rpc_method(self.query_data)
        self.register_rpc_method(self.change_to)

        # Introspection
        self.register_rpc_method(self.get_capabilities)
        self.register_rpc_method(self.get_pymodaq_settings)
        self.register_rpc_method(self.set_info)
        self.register_rpc_method(self.subscribe_director)
        self.register_rpc_method(self.unsubscribe_director)
        self.register_rpc_method(self.query_data_continuous)
        self.register_rpc_method(self.stop_continuous)
        self.register_rpc_method(self.set_published_names)
        self.register_rpc_method(self.get_published_names)
        self.register_rpc_method(self.get_grabbed_names)

        # # Heartbeat — used by directors to check connectivity
        # self.register_rpc_method(self.pong)

        # Legacy aliases — keep existing directors working without changes
        self.register_rpc_method(self._legacy_grab, name='grab')
        self.register_rpc_method(self._legacy_grab, name='snap')
        self.register_rpc_method(self._legacy_grab, name='get_actuator_value')
        self.register_rpc_method(self._legacy_move_abs, name='move_abs')
        self.register_rpc_method(self._legacy_move_rel, name='move_rel')
        self.register_rpc_method(self._legacy_move_home, name='move_home')

    # ── Primary interface ──────────────────────────────────────────────────────

    def query_data(
        self,
        names=None,
        fresh: bool = True,
    ) -> Optional[str]:
        """Read observables from the device and publish on the data channel.

        Accepts either a single observable name or a list of names.

        Parameters
        ----------
        names:
            Name(s) of observables to read.  A single ``str`` is accepted and
            treated as ``[names]``.  ``None`` means read all.
        fresh:
            If ``True``, trigger a new hardware acquisition (costly but up-to-date).
            If ``False``, re-publish the last cached :class:`DataToExport` without
            touching hardware.

        Returns
        -------
        str or None
            Hex-encoded conversation ID of the ZMQ publish, so the caller can
            correlate this RPC response with the matching frame on the data channel.
            ``None`` if no data was available to publish.
        """
        if isinstance(names, str):
            names = [names]
        if fresh:
            try:
                dte = self.device.read(names)
            except Exception:
                logger.exception("query_data: device.read() raised an exception")
                return None
            if dte is not None:
                self._last_data = dte
                return self._publish(dte)
        else:
            if self._last_data is not None:
                return self._publish(self._last_data)
        return None

    def change_to(self, name, value=None) -> Optional[str]:
        """Write one or more variables on the device.

        Accepts either a single name/value pair or a dict of name→value pairs
        for a multi-variable update in one RPC call.

        Parameters
        ----------
        name : str | dict
            Variable name (str) for a single update, or a dict mapping
            variable names to new values for a multi-variable update.
        value :
            New value. Required when *name* is a str; ignored when *name* is a dict.
        """
        if isinstance(name, dict):
            for k, v in name.items():
                self.device.write(k, v)
            written_names = list(name.keys())
        else:
            self.device.write(name, value)
            written_names = [name]
        # Publish only the written channel(s) so unrelated directors are not
        # disturbed (e.g. a stage move must not push a spectrum frame to the viewer).
        try:
            return self.query_data(names=written_names, fresh=True)
        except Exception:
            logger.exception("change_to: auto-publish failed")
            return None

    # ── Introspection ──────────────────────────────────────────────────────────

    def get_capabilities(self) -> dict:
        """Return the device's :class:`Capabilities` as a JSON-compatible dict.

        Returns
        -------
        dict
            Result of :meth:`Capabilities.to_dict`.
        """
        caps = infer_capabilities(self.device)
        return caps.to_dict()

    def get_pymodaq_settings(self) -> Optional[str]:
        """Return the device's parameter tree as an XML string.

        Returns ``None`` if the device does not expose settings.
        """
        if hasattr(self.device, 'get_settings'):
            result = self.device.get_settings()
            if isinstance(result, bytes):
                return result.decode()
            return result
        return None

    def set_info(self, path: str, value: Any) -> None:
        """Update a setting on the device and broadcast to registered directors.

        Parameters
        ----------
        path:
            Dot-separated parameter path (e.g. ``'integration_time'``).
        value:
            New value for the parameter.
        """
        if hasattr(self.device, 'set_info'):
            self.device.set_info(path, value)
        self._broadcast_settings()

    def subscribe_director(self, name: str) -> None:
        """Register a director to receive settings broadcasts.

        Parameters
        ----------
        name:
            Full LECO name of the director (``namespace.component``).
        """
        self._director_registry.add(name)
        logger.debug("Director '%s' subscribed to actor '%s'.", name, self.name)

    def unsubscribe_director(self, name: str) -> None:
        """Remove a director from settings broadcasts.

        Parameters
        ----------
        name:
            Full LECO name of the director.
        """
        self._director_registry.discard(name)
        logger.debug("Director '%s' unsubscribed from actor '%s'.", name, self.name)

    def set_published_names(self, names: Optional[list]) -> None:
        """Configure which observable/variable names are published in continuous mode.

        Parameters
        ----------
        names:
            List of names to publish.  ``None`` removes the filter (publish everything).
            An empty list disables all continuous publication.
        """
        self._published_names = set(names) if names is not None else None
        logger.debug("'%s' published_names set to: %s", self.name, self._published_names)

    def get_published_names(self) -> Optional[list]:
        """Return the current continuous-publish filter.

        Returns
        -------
        list[str] or None
            Sorted list of names that will be published in continuous mode,
            or ``None`` if no filter is set (all names are published).
        """
        if self._published_names is None:
            return None
        return sorted(self._published_names)

    def get_grabbed_names(self) -> Optional[list]:
        """Return the names currently being grabbed in continuous mode.

        Returns
        -------
        list[str] or None
            Sorted list of names actively grabbed, or ``None`` when not in
            continuous mode or when grabbing all names (no filter).
        """
        if self._grabbed_names is None:
            return None
        return sorted(self._grabbed_names)

    # def pong(self) -> str:
    #     """Heartbeat reply — called by directors to verify connectivity."""
    #     return "pong"
    # ── Data channel (periodic readout) ───────────────────────────────────────

    def read_publish(self, device, publisher: DataPublisher) -> None:
        """Called by the periodic timer: read device and publish on data channel.

        Override of :meth:`pyleco.actors.Actor.read_publish`.
        Respects :attr:`_published_names`: if set to an empty set, skips publication.
        """
        if self._stop_grab_flag:
            return
        # If _published_names is explicitly set to empty, nothing to publish.
        if self._published_names is not None and not self._published_names:
            return
        names = list(self._published_names) if self._published_names is not None else None
        try:
            dte = device.read(names)
        except Exception:
            logger.exception("read_publish: device.read() raised an exception")
            return
        if dte is not None:
            self._last_data = dte
            self._publish(dte)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _publish(self, dte) -> Optional[str]:
        """Serialize *dte* and publish each channel on its own sub-topic.

        Each :class:`DataWithAxes` in *dte* is wrapped in a single-DWA
        :class:`DataToExport` and published to ``"{actor_name}/{dwa.name}"``.
        Directors subscribe to their specific channel topic so the ZMQ broker
        drops irrelevant frames before they reach Python.

        When per-channel proxy overrides are configured, each ``DataWithAxes``
        is routed to the publisher whose proxy was selected for that channel in
        the actor GUI; channels with no override go to the default publisher.

        Returns
        -------
        str or None
            Hex-encoded conversation ID embedded in the ZMQ frame header, or
            ``None`` if serialization / publish failed.  Directors can compare
            this value against the ``cid`` field in the ``'data_received'``
            :class:`ThreadCommand` to match a specific frame.
        """
        try:
            from serializall import SerializableFactory
            factory = SerializableFactory()
            cid = generate_conversation_id()

            # Publish each DWA to its own sub-topic: "{actor_name}/{dwa.name}".
            # Directors subscribe to the per-channel topic so ZMQ drops irrelevant
            # frames before they reach Python — no name filtering needed at the director.
            # One conversation_id is shared across all DWAs in this call so callers can
            # correlate the RPC return value with the matching ZMQ frames.
            for dwa in dte.data:
                sub_dte = DataToExport(name=dwa.name, data=[dwa])
                payload: bytes = factory.get_apply_serializer(sub_dte)
                topic = f"{self.name}/{dwa.name}"
                # Route to per-channel proxy publisher if configured, else default.
                key = self._channel_proxy_keys.get(dwa.name)
                pub = self._extra_publishers.get(key) if key is not None else None
                (pub or self.publisher).send_data(
                    data=payload, topic=topic, conversation_id=cid
                )
            return cid.hex()
        except Exception:
            logger.exception("_publish: failed to serialize / publish DataToExport")
            return None

    def _broadcast_settings(self) -> None:
        """Push updated settings XML to all registered directors."""
        if not self._director_registry:
            return
        settings_xml = self.get_pymodaq_settings()
        if settings_xml is None:
            return
        try:
            communicator = self.get_communicator()
            for director_name in list(self._director_registry):
                try:
                    communicator.ask_rpc(
                        receiver=director_name,
                        method='set_director_settings',
                        settings=settings_xml,
                    )
                except Exception:
                    logger.warning(
                        "Failed to broadcast settings to director '%s'; "
                        "removing from registry.",
                        director_name,
                    )
                    self._director_registry.discard(director_name)
        except Exception:
            logger.exception("_broadcast_settings: failed to get communicator")

    def _broadcast_grab_status(self) -> None:
        """Push current continuous-grab status to all registered directors."""
        if not self._director_registry:
            return
        is_continuous = self._grab_thread is not None and self._grab_thread.is_alive()
        grabbed = self.get_grabbed_names()
        try:
            communicator = self.get_communicator()
            for director_name in list(self._director_registry):
                try:
                    communicator.ask_rpc(
                        receiver=director_name,
                        method='on_grab_status',
                        grabbed_names=grabbed,
                        is_continuous=is_continuous,
                    )
                except Exception:
                    logger.warning(
                        "Failed to broadcast grab status to director '%s'.",
                        director_name,
                    )
        except Exception:
            logger.exception("_broadcast_grab_status: failed to get communicator")

    # ── Continuous acquisition ─────────────────────────────────────────────────

    def query_data_continuous(self, rate_hz: float = 0) -> None:
        """Start a continuous acquisition loop that publishes on the data channel.

        Idempotent: if the loop is already running a second call has no effect
        beyond broadcasting the current grab status to all registered directors
        (so their GUIs can mirror the state).

        Parameters
        ----------
        rate_hz:
            Target publish rate in frames per second.
            ``0`` (default) means as fast as ``device.read()`` allows.

        Notes
        -----
        ``device.read()`` is called from a background thread; avoid issuing
        concurrent ``query_data`` RPC calls while continuous acquisition is running.
        The names published are determined by :attr:`_published_names` at the moment
        this method is called and do not change for the lifetime of the loop.
        """
        if self._grab_thread is not None and self._grab_thread.is_alive():
            # Already running — broadcast current status so the caller's GUI mirrors it.
            logger.debug(
                "query_data_continuous: loop already running on '%s'; broadcasting status.",
                self.name,
            )
            self._broadcast_grab_status()
            return
        self._stop_grab_flag = False
        # Snapshot the publish filter at grab-start time.
        self._grabbed_names = (
            set(self._published_names) if self._published_names is not None else None
        )
        self._grab_thread = threading.Thread(
            target=self._grab_loop,
            args=(rate_hz,),
            daemon=True,
            name=f"continuous-{self.name}",
        )
        self._grab_thread.start()
        self._broadcast_grab_status()

    def stop_continuous(self) -> None:
        """Stop the continuous acquisition loop and notify registered directors.

        Sets the stop flag, waits up to 2 s for the loop thread to exit,
        clears the grabbed-names snapshot, and broadcasts the updated status.
        Safe to call even when no continuous acquisition is running.
        """
        self._stop_grab_flag = True
        if self._grab_thread is not None and self._grab_thread.is_alive():
            self._grab_thread.join(timeout=2.0)
        self._grab_thread = None
        self._grabbed_names = None
        self._broadcast_grab_status()

    def _grab_loop(self, rate_hz: float) -> None:
        """Background thread body for continuous acquisition."""
        interval = 1.0 / rate_hz if rate_hz > 0 else 0.0
        # Snapshot once — the filter does not change mid-loop.
        names = list(self._grabbed_names) if self._grabbed_names is not None else None
        while not self._stop_grab_flag:
            t0 = time.monotonic()
            try:
                dte = self.device.read(names)
            except Exception:
                logger.exception("_grab_loop: device.read() failed; stopping")
                break
            if dte is not None:
                self._last_data = dte
                self._publish(dte)
            if interval > 0:
                elapsed = time.monotonic() - t0
                remaining = interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)

    # ── Legacy aliases ─────────────────────────────────────────────────────────

    def _legacy_grab(self) -> None:
        """Legacy alias for ``grab`` / ``snap`` / ``get_actuator_value`` RPC names.

        Triggers :meth:`query_data` with ``fresh=True``.
        """
        self._stop_grab_flag = False
        self.query_data(names=None, fresh=True)

    def _legacy_move_abs(self, position: float) -> None:
        """Legacy alias: ``move_abs(position)`` → ``change_to('position', position)``."""
        self.change_to('position', position)

    def _legacy_move_rel(self, position: float) -> None:
        """Legacy alias: ``move_rel(delta)`` — relative move.

        Delegates to ``device.move_rel(delta)`` if available, otherwise raises
        :class:`NotImplementedError`.
        """
        if hasattr(self.device, 'move_rel'):
            self.device.move_rel(position)
        else:
            raise NotImplementedError(
                "move_rel requires device.move_rel(); "
                "use change_to() with an absolute target instead."
            )

    def _legacy_move_home(self) -> None:
        """Legacy alias: ``move_home()`` — move to home position.

        Delegates to ``device.home()`` or ``device.move_home()`` if available,
        otherwise writes ``0.0`` to the ``'position'`` variable.
        """
        if hasattr(self.device, 'home'):
            self.device.home()
        elif hasattr(self.device, 'move_home'):
            self.device.move_home()
        else:
            self.change_to('position', 0.0)


# ── CLI entry point ────────────────────────────────────────────────────────────

def actor_main() -> None:  # pragma: no cover
    """CLI entry point: ``pymodaq-actor``."""
    import argparse
    import importlib
    import threading

    parser = argparse.ArgumentParser(
        prog='pymodaq-actor',
        description='Launch a headless PyMoDAQ hardware actor.',
    )
    parser.add_argument(
        '--plugin',
        required=True,
        metavar='MODULE.CLASS',
        help=(
            'Fully qualified plugin class, e.g. '
            '"pymodaq_plugins_andor.daq_2Dviewer_andor.DAQ_2DViewer_Andor"'
        ),
    )
    parser.add_argument(
        '--name',
        required=True,
        help='LECO actor name (used for addressing and data-channel topic).',
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Hostname of the LECO Coordinator (default: localhost).',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help='Port of the LECO Coordinator (default: pyleco default).',
    )
    parser.add_argument(
        '--polling',
        type=float,
        default=-1.0,
        help='Periodic readout interval in seconds (-1 = disabled, default).',
    )
    args = parser.parse_args()

    # Dynamically load the plugin class
    module_path, class_name = args.plugin.rsplit('.', 1)
    module = importlib.import_module(module_path)
    device_class = getattr(module, class_name)

    actor_kwargs: dict = {'host': args.host}
    if args.port is not None:
        actor_kwargs['port'] = args.port

    actor = PymodaqActor(
        name=args.name,
        device_class=device_class,
        periodic_reading=args.polling,
        **actor_kwargs,
    )

    stop_event = threading.Event()
    try:
        actor.listen(stop_event=stop_event)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        actor.disconnect()
