"""PymodaqActor — headless hardware process for PyMoDAQ.

Wraps :class:`pyleco.actors.Actor` and exposes a unified hardware interface over LECO via
an **instruction-queue hardware loop**:

- A single *hardware thread* owns the device exclusively.
- All other threads (the pyleco listen loop, RPC handlers) communicate via
  :class:`queue.Queue` + :class:`threading.Event`.
- No lock on ``device.read()`` / ``device.write()`` is needed — structural guarantee.

Primary RPC API::

    query_data(names, count, fresh, period)  — read observables
    change_to(name, value)                   — write a variable
    stop(names)                              — stop acquiring named observables
    get_acquisition_status()                 — current read_list snapshot

**Device interface** — the object passed as ``device_class`` must implement::

    device.connect()                                          — open hardware
    device.close()                                            — close hardware
    device.read(names: list[str] | None = None) -> DataToExport
    device.write(name: str, value: Any) -> None

and may optionally implement::

    device.capabilities  -> Capabilities  (else infer_capabilities(device) is used)
    device.get_settings() -> str          (XML parameter tree)
    device.set_info(path: str, value)     (update a parameter)
    device.move_rel(delta: float)         (relative move)
    device.home()                         (move to home position)

No Qt import in this module.
"""
from __future__ import annotations

import logging
import math
import queue
import threading
import time
import warnings
from dataclasses import dataclass
from typing import Any, Optional

from pyleco.actors.actor import Actor
from pyleco.core import PROXY_RECEIVING_PORT
from pyleco.core.serialization import generate_conversation_id
from pyleco.utils.data_publisher import DataPublisher

from pymodaq_data import DataToExport

from pymodaq.control_modules.capabilities import Capabilities, infer_capabilities

logger = logging.getLogger(__name__)


# ── Instruction data structures (Phase 0) ─────────────────────────────────────

@dataclass
class ReadRequest:
    """Request to read one or more observables from the hardware."""
    names: Optional[list[str]]  # None = read all observables
    count: float                 # 1 = snap; math.inf = continuous
    period: float                # seconds between reads; 0 = as fast as possible
    requester: str               # full LECO name of the director, e.g. "localhost.det_dir_1"
    req_id: bytes                # pre-generated conversation_id; used as ZMQ cid


@dataclass
class WriteInstruction:
    """Request to write one or more variables on the hardware."""
    name: Any   # str = single; dict = multi-write; tuple('settings', path) = settings write
    value: Any  # ignored when name is a dict
    requester: str
    req_id: bytes


@dataclass
class StopInstruction:
    """Request to stop acquiring one or more observables."""
    names: Optional[list[str]]  # None = stop all
    requester: str


# ── Actor ──────────────────────────────────────────────────────────────────────

class PymodaqActor(Actor):
    """Hardware actor for PyMoDAQ — instruction-queue architecture.

    Parameters
    ----------
    name:
        LECO actor name (used as ZMQ topic for data-channel publications).
    device_class:
        Class of the hardware plugin.  Instantiated by :meth:`connect`.
    periodic_reading:
        **Deprecated** — has no effect.  Use ``query_data(count=math.inf, period=...)``
        instead.  Will be removed in a future release.
    **kwargs:
        Forwarded to :class:`pyleco.actors.Actor` (``host``, ``port``, ``context``, …).
    """

    _director_registry: set[str]
    _last_data: Optional[Any]

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
        if periodic_reading != -1:
            warnings.warn(
                "The 'periodic_reading' parameter is deprecated and has no effect. "
                "Use query_data(count=math.inf, period=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        context = kwargs.get('context')
        super().__init__(name=name, device_class=device_class,
                         periodic_reading=periodic_reading, **kwargs)
        # Always recreate the publisher so we can honour proxy_host/proxy_port.
        self.publisher.close()
        self.publisher = DataPublisher(
            full_name=name,
            host=proxy_host,
            port=proxy_port,
            context=context,
        )
        # Per-channel publisher routing.
        self._channel_proxy_keys: dict[str, tuple[str, int]] = {}
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

        # Instruction-queue hardware loop state
        self._instruction_queue: queue.Queue = queue.Queue()
        self._new_instruction_event: threading.Event = threading.Event()
        self._hw_stop_event: threading.Event = threading.Event()
        self._read_list: dict = {}        # key (frozenset|None) → ReadRequest
        self._last_read_time: dict = {}   # key → float (monotonic)
        self._write_pending: dict = {}    # name → (value, req_id, requester)
        self._hw_thread: Optional[threading.Thread] = None

    # ── Hardware lifecycle ─────────────────────────────────────────────────────

    def connect(self, *args, **kwargs) -> None:
        """Instantiate the device class, open hardware, start the hardware loop.

        Stops the pyleco periodic timer — the hardware loop replaces it.
        """
        super().connect(*args, **kwargs)   # sets self.device = device_class(...)
        try:
            self.device.connect()
        except AttributeError:
            logger.debug("Device has no connect() method; skipping hardware open.")
        # Stop pyleco's periodic timer; hardware loop is the sole read driver.
        self.stop_timer()
        # Start the hardware loop thread.
        self._hw_stop_event.clear()
        self._hw_thread = threading.Thread(
            target=self._hardware_loop,
            daemon=True,
            name=f"hw-loop-{self.name}",
        )
        self._hw_thread.start()

    def disconnect(self) -> None:
        """Stop the hardware loop, close the device, clean up publishers."""
        # Stop hardware loop first.
        self._hw_stop_event.set()
        self._new_instruction_event.set()
        if self._hw_thread is not None and self._hw_thread.is_alive():
            self._hw_thread.join(timeout=2.0)
        self._hw_thread = None

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
        self.register_rpc_method(self.stop)
        self.register_rpc_method(self.get_acquisition_status)
        self.register_rpc_method(self.get_read_list)

        # Introspection
        self.register_rpc_method(self.get_capabilities)
        self.register_rpc_method(self.get_pymodaq_settings)
        self.register_rpc_method(self.get_actor_pub_topic)
        self.register_rpc_method(self.set_info)
        self.register_rpc_method(self.subscribe_director)
        self.register_rpc_method(self.unsubscribe_director)

        # Deprecated aliases (kept for one release cycle)
        self.register_rpc_method(self.query_data_continuous)
        self.register_rpc_method(self.stop_continuous)
        self.register_rpc_method(self.get_grabbed_names)
        self.register_rpc_method(self.set_published_names)
        self.register_rpc_method(self.get_published_names)

        # Manager introspection
        self.register_rpc_method(self.get_role)
        self.register_rpc_method(self.shutdown)

        # Legacy aliases — keep existing directors working without changes
        self.register_rpc_method(self._legacy_grab, name='grab')
        self.register_rpc_method(self._legacy_grab, name='snap')
        self.register_rpc_method(self._legacy_grab, name='get_actuator_value')
        self.register_rpc_method(self._legacy_move_abs, name='move_abs')
        self.register_rpc_method(self._legacy_move_rel, name='move_rel')
        self.register_rpc_method(self._legacy_move_home, name='move_home')

    # ── Hardware loop (Phase 1) ────────────────────────────────────────────────

    def _hardware_loop(self) -> None:
        """Single hardware thread — sole owner of ``device.read()`` / ``device.write()``."""
        _prev_keys: frozenset = frozenset()

        while not self._hw_stop_event.is_set():
            # 1. Drain instruction queue (non-blocking).
            self._process_pending_instructions()

            # 2. Execute all pending writes first (writes before reads in same tick).
            for name, (value, req_id, requester) in list(self._write_pending.items()):
                try:
                    if isinstance(name, tuple) and name[0] == 'settings':
                        # Settings write via set_info.
                        path = name[1]
                        if hasattr(self.device, 'set_info'):
                            self.device.set_info(path, value)
                        try:
                            self._broadcast_settings()
                        except Exception:
                            pass
                    else:
                        self.device.write(name, value)
                        # Schedule one-shot readback if channel not already in continuous read.
                        rb_key = frozenset([name])
                        if rb_key not in self._read_list and None not in self._read_list:
                            self._read_list[rb_key] = ReadRequest(
                                names=[name], count=1, period=0.0,
                                requester=requester, req_id=req_id,
                            )
                            self._last_read_time.setdefault(rb_key, 0.0)
                except Exception:
                    logger.exception("hardware loop: write failed for %s", name)
            self._write_pending.clear()

            # 3. Execute reads that are due.
            now = time.monotonic()
            for key in list(self._read_list.keys()):
                req = self._read_list.get(key)
                if req is None:
                    continue
                last_t = self._last_read_time.get(key, 0.0)
                if now - last_t >= req.period:
                    try:
                        dte = self.device.read(req.names)
                    except Exception as exc:
                        logger.exception(
                            "hardware loop: device.read() failed for %s", req.names
                        )
                        self._report_error(req.requester, req.req_id, str(exc))
                        del self._read_list[key]
                        self._last_read_time.pop(key, None)
                        continue
                    if dte is not None:
                        self._last_data = dte
                        self._publish(dte, cid=req.req_id)
                    self._last_read_time[key] = now
                    req.count -= 1
                    if req.count <= 0:
                        del self._read_list[key]
                        self._last_read_time.pop(key, None)

            # 4. Broadcast acquisition status if read_list changed this tick.
            current_keys = frozenset(self._read_list.keys())
            if current_keys != _prev_keys:
                try:
                    self._broadcast_acquisition_status()
                except Exception:
                    pass
                _prev_keys = current_keys

            # 5. Sleep until next read is due (interruptible by new instructions).
            sleep_time = max(0.0, self._time_until_next_due())
            self._new_instruction_event.wait(timeout=sleep_time if sleep_time > 0 else 0.05)
            self._new_instruction_event.clear()

    def _process_pending_instructions(self) -> None:
        """Drain the instruction queue (non-blocking)."""
        while True:
            try:
                instr = self._instruction_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(instr, ReadRequest):
                key = frozenset(instr.names) if instr.names is not None else None
                existing = self._read_list.get(key)
                if existing is not None:
                    # Merge: min period; math.inf wins over finite count.
                    merged_period = min(existing.period, instr.period)
                    merged_count = (
                        math.inf
                        if (math.isinf(existing.count) or math.isinf(instr.count))
                        else max(existing.count, instr.count)
                    )
                    instr = ReadRequest(
                        names=instr.names,
                        count=merged_count,
                        period=merged_period,
                        requester=instr.requester,
                        req_id=instr.req_id,
                    )
                self._read_list[key] = instr
                if key not in self._last_read_time:
                    self._last_read_time[key] = 0.0  # fire immediately on first read

            elif isinstance(instr, WriteInstruction):
                if isinstance(instr.name, dict):
                    for k, v in instr.name.items():
                        self._write_pending[k] = (v, instr.req_id, instr.requester)
                elif isinstance(instr.name, list):
                    # change_to(name=[...], value=[...]) — iterate in zip
                    values = instr.value if isinstance(instr.value, list) else [instr.value]
                    for k, v in zip(instr.name, values):
                        self._write_pending[k] = (v, instr.req_id, instr.requester)
                else:
                    self._write_pending[instr.name] = (
                        instr.value, instr.req_id, instr.requester
                    )

            elif isinstance(instr, StopInstruction):
                if instr.names is None:
                    self._read_list.clear()
                    self._last_read_time.clear()
                else:
                    key = frozenset(instr.names)
                    self._read_list.pop(key, None)
                    self._last_read_time.pop(key, None)

    def _time_until_next_due(self) -> float:
        """Seconds until the next read is due.  Returns 0.05 if no reads pending."""
        if not self._read_list:
            return 0.05
        now = time.monotonic()
        min_wait = float('inf')
        for key, req in self._read_list.items():
            last_t = self._last_read_time.get(key, 0.0)
            remaining = req.period - (now - last_t)
            min_wait = min(min_wait, remaining)
        return max(0.0, min_wait)

    def _report_error(self, requester: str, req_id: bytes, message: str) -> None:
        """Send an ``on_hardware_error`` RPC to the requester."""
        if not requester:
            return
        try:
            comm = self.get_communicator()
            comm.ask_rpc(
                receiver=requester,
                method='on_hardware_error',
                req_id=req_id.hex(),
                message=message,
            )
        except Exception:
            pass

    # ── Primary interface (Phase 2) ────────────────────────────────────────────

    def query_data(
        self,
        names=None,
        count: float = 1,
        fresh: bool = True,
        period: float = 0.0,
    ) -> Optional[str]:
        """Read observables from the device and publish on the data channel.

        Parameters
        ----------
        names:
            Name(s) of observables to read.  A single ``str`` is accepted and
            treated as ``[names]``.  ``None`` means read all.
        count:
            Number of reads: ``1`` for a one-shot snap; ``math.inf`` for
            continuous acquisition until :meth:`stop` is called.
        fresh:
            If ``True`` (default), enqueue a :class:`ReadRequest`; data arrives
            later on the ZMQ data channel.
            If ``False``, re-publish the last cached :class:`DataToExport`
            synchronously without touching hardware.
        period:
            Minimum seconds between reads (``0`` = as fast as hardware allows).

        Returns
        -------
        str or None
            Hex-encoded conversation ID of the ZMQ publish.  For ``fresh=True``,
            this is the ID that will be used when the hardware loop publishes —
            the director can correlate ZMQ frames using this value.
            ``None`` if no data was available (``fresh=False`` with empty cache).
        """
        if isinstance(names, str):
            names = [names]
        if not fresh:
            if self._last_data is not None:
                return self._publish(self._last_data)
            return None
        # fresh=True: enqueue ReadRequest; hardware loop processes asynchronously.
        req_id = generate_conversation_id()
        req = ReadRequest(
            names=names,
            count=float(count),
            period=float(period),
            requester='',
            req_id=req_id,
        )
        self._instruction_queue.put(req)
        self._new_instruction_event.set()
        return req_id.hex()

    def change_to(self, name, value=None) -> Optional[str]:
        """Write one or more variables on the device (enqueued for hardware thread).

        Parameters
        ----------
        name : str | dict
            Variable name (str) for a single update, or a dict mapping
            variable names to new values for a multi-variable update.
        value :
            New value. Required when *name* is a str; ignored when *name* is a dict.

        Returns
        -------
        str
            Hex-encoded conversation ID; the hardware thread uses this ID for
            the auto-readback ZMQ publish after the write completes.
        """
        req_id = generate_conversation_id()
        instr = WriteInstruction(name=name, value=value, requester='', req_id=req_id)
        self._instruction_queue.put(instr)
        self._new_instruction_event.set()
        return req_id.hex()

    def stop(self, names=None) -> None:
        """Stop acquiring the named observables (global stop — affects all directors).

        Parameters
        ----------
        names:
            List of observable names to stop.  ``None`` (default) stops all.
        """
        instr = StopInstruction(names=names, requester='')
        self._instruction_queue.put(instr)
        self._new_instruction_event.set()

    def get_acquisition_status(self) -> dict:
        """Return the current acquisition state as a JSON-compatible dict.

        Returns
        -------
        dict
            ``{"read_list": {...}, "is_grabbing": bool}``
        """
        read_list_serial: dict = {}
        for key, req in self._read_list.items():
            if key is None:
                channel_key = '__all__'
            else:
                channel_key = '/'.join(sorted(key))
            read_list_serial[channel_key] = {
                'names': req.names,
                'count': None if math.isinf(req.count) else req.count,
                'period': req.period,
                'requester': req.requester,
            }
        return {
            'read_list': read_list_serial,
            'is_grabbing': bool(self._read_list),
        }

    def get_read_list(self) -> dict:
        """Return the current read list.  Alias for :meth:`get_acquisition_status`."""
        return self.get_acquisition_status()

    # ── Introspection ──────────────────────────────────────────────────────────

    def get_capabilities(self) -> dict:
        """Return the device's :class:`Capabilities` as a JSON-compatible dict."""
        caps = infer_capabilities(self.device)
        return caps.to_dict()

    def get_pymodaq_settings(self) -> Optional[str]:
        """Return the device's parameter tree as an XML string."""
        if hasattr(self.device, 'get_settings'):
            result = self.device.get_settings()
            if isinstance(result, bytes):
                return result.decode()
            return result
        return None

    def get_actor_pub_topic(self) -> str:
        """Return the ZMQ publish topic base used by this actor."""
        return self.publisher.full_name

    def get_role(self) -> dict:
        """Return role dict for network manager discovery."""
        return {"role": "actor", "host": self.publisher.full_name}

    def shutdown(self) -> None:
        """Stop hardware loop, notify directors, signal listen loop to exit."""
        # Stop hardware loop.
        self._hw_stop_event.set()
        self._new_instruction_event.set()
        if self._hw_thread is not None and self._hw_thread.is_alive():
            self._hw_thread.join(timeout=2.0)
        self._hw_thread = None

        # Notify registered directors.
        for director_name in list(self._director_registry):
            try:
                communicator = self.get_communicator()
                communicator.ask_rpc(receiver=director_name, method='disconnect')
            except Exception:
                logger.debug("shutdown: could not notify director '%s'", director_name)
        self._director_registry.clear()

        # Signal the listen loop to exit.
        try:
            stop_event = getattr(self, '_stop_event', None)
            if stop_event is not None:
                stop_event.set()
        except Exception:
            pass
        logger.info("Actor '%s' shutdown complete.", self.name)

    def set_info(self, path: str, value: Any) -> None:
        """Update a setting on the device (enqueued so it runs before next read).

        Parameters
        ----------
        path:
            Dot-separated parameter path (e.g. ``'integration_time'``).
        value:
            New value for the parameter.
        """
        req_id = generate_conversation_id()
        instr = WriteInstruction(
            name=('settings', path),
            value=value,
            requester='',
            req_id=req_id,
        )
        self._instruction_queue.put(instr)
        self._new_instruction_event.set()

    def subscribe_director(self, name: str) -> None:
        """Register a director to receive settings and acquisition status broadcasts."""
        self._director_registry.add(name)
        logger.debug("Director '%s' subscribed to actor '%s'.", name, self.name)

    def unsubscribe_director(self, name: str) -> None:
        """Remove a director from broadcasts."""
        self._director_registry.discard(name)
        logger.debug("Director '%s' unsubscribed from actor '%s'.", name, self.name)

    # ── Deprecated aliases (kept for one release cycle) ───────────────────────

    def query_data_continuous(self, rate_hz: float = 0) -> None:
        """Deprecated: use ``query_data(count=math.inf, period=1/rate_hz)``."""
        period = 1.0 / rate_hz if rate_hz > 0 else 0.0
        self.query_data(names=None, count=math.inf, fresh=True, period=period)

    def stop_continuous(self) -> None:
        """Deprecated: use ``stop(names=None)``."""
        self.stop(names=None)

    def get_grabbed_names(self) -> Optional[list]:
        """Deprecated: use ``get_read_list()``."""
        if not self._read_list:
            return None
        names: list[str] = []
        for key in self._read_list:
            if key is None:
                return None  # "all channels" entry
            names.extend(key)
        return sorted(set(names))

    def set_published_names(self, names: Optional[list]) -> None:
        """Deprecated — no-op.  Use the read_list API instead."""
        logger.warning(
            "set_published_names() is deprecated and has no effect. "
            "Use query_data(count=math.inf) to control what the actor reads."
        )

    def get_published_names(self) -> Optional[list]:
        """Deprecated: use ``get_read_list()``."""
        return self.get_grabbed_names()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _publish(self, dte, cid=None) -> Optional[str]:
        """Serialize *dte* and publish each channel on its own sub-topic.

        Parameters
        ----------
        dte:
            :class:`DataToExport` to publish.
        cid:
            Optional conversation ID (:class:`bytes`).  Generated if ``None``.

        Returns
        -------
        str or None
            Hex-encoded conversation ID, or ``None`` on failure.
        """
        try:
            from serializall import SerializableFactory
            factory = SerializableFactory()
            if cid is None:
                cid = generate_conversation_id()
            base_topic = self.publisher.full_name
            for dwa in dte.data:
                sub_dte = DataToExport(name=dwa.name, data=[dwa])
                payload: bytes = factory.get_apply_serializer(sub_dte)
                topic = f"{base_topic}/{dwa.name}"
                key = self._channel_proxy_keys.get(dwa.name)
                pub = self._extra_publishers.get(key) if key is not None else None
                (pub or self.publisher).send_data(
                    data=payload, topic=topic, conversation_id=cid,
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
                        "Failed to broadcast settings to director '%s'; removing.",
                        director_name,
                    )
                    self._director_registry.discard(director_name)
        except Exception:
            logger.exception("_broadcast_settings: failed to get communicator")

    def _broadcast_acquisition_status(self) -> None:
        """Push current acquisition status to all registered directors."""
        if not self._director_registry:
            return
        status = self.get_acquisition_status()
        try:
            communicator = self.get_communicator()
            for director_name in list(self._director_registry):
                try:
                    communicator.ask_rpc(
                        receiver=director_name,
                        method='on_acquisition_status',
                        read_list=status['read_list'],
                        is_grabbing=status['is_grabbing'],
                    )
                except Exception:
                    logger.warning(
                        "Failed to broadcast acquisition status to '%s'.", director_name
                    )
        except Exception:
            logger.exception("_broadcast_acquisition_status: failed to get communicator")

    # ── Legacy RPC aliases ─────────────────────────────────────────────────────

    def _legacy_grab(self) -> None:
        """Legacy alias for ``grab`` / ``snap`` / ``get_actuator_value`` RPC names."""
        self.query_data(names=None, count=1, fresh=True)

    def _legacy_move_abs(self, position: float) -> None:
        """Legacy alias: ``move_abs(position)`` → ``change_to('position', position)``."""
        self.change_to('position', position)

    def _legacy_move_rel(self, position: float) -> None:
        """Legacy alias: ``move_rel(delta)`` — relative move."""
        if hasattr(self.device, 'move_rel'):
            self.device.move_rel(position)
        else:
            raise NotImplementedError(
                "move_rel requires device.move_rel(); "
                "use change_to() with an absolute target instead."
            )

    def _legacy_move_home(self) -> None:
        """Legacy alias: ``move_home()`` — move to home position."""
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

    parser = argparse.ArgumentParser(
        prog='pymodaq-actor',
        description='Launch a headless PyMoDAQ hardware actor.',
    )
    parser.add_argument(
        '--plugin', required=True, metavar='MODULE.CLASS',
        help='Fully qualified plugin class.',
    )
    parser.add_argument('--name', required=True,
                        help='LECO actor name.')
    parser.add_argument('--host', default='localhost',
                        help='Hostname of the LECO Coordinator (default: localhost).')
    parser.add_argument('--port', type=int, default=None,
                        help='Port of the LECO Coordinator.')
    args = parser.parse_args()

    module_path, class_name = args.plugin.rsplit('.', 1)
    module = importlib.import_module(module_path)
    device_class = getattr(module, class_name)

    actor_kwargs: dict = {'host': args.host}
    if args.port is not None:
        actor_kwargs['port'] = args.port

    actor = PymodaqActor(name=args.name, device_class=device_class, **actor_kwargs)

    stop_event = threading.Event()
    try:
        actor.listen(stop_event=stop_event)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        actor.disconnect()
