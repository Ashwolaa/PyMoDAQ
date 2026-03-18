"""LECO Network Monitor — pure-Python, no Qt.

Data model and polling logic for the LECO Network Manager GUI (Phase 1).

Provides:
    - :class:`ComponentRecord` — snapshot of a single LECO component
    - :class:`ProxyRecord`     — a ZMQ PUB/SUB proxy (managed or external)
    - :class:`CoordinatorRecord` — the LECO coordinator process
    - :class:`LECONetworkMonitor` — orchestrates discovery, polling, subprocess lifecycle

No Qt imports.  The GUI layer (Phase 2) wraps the plain-callable callbacks in Qt
signals and drives the poll timers with ``QTimer``.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ComponentRecord:
    """Snapshot of a single LECO component (actor, director, coordinator, …)."""

    name: str
    """Short component name, e.g. ``'stage'``."""

    full_name: str
    """Namespace-qualified name, e.g. ``'localhost.stage'``."""

    role: str
    """One of ``'actor'``, ``'director'``, ``'coordinator'``, ``'unknown'``."""

    host: Optional[str] = None
    """Source host reported by ``get_role()`` (actor: bind addr; director: hostname)."""

    # Actor-only detail (populated by refresh_actor_details)
    capabilities: Optional[dict] = None
    """Raw capabilities dict (from ``get_capabilities()`` RPC)."""

    grabbed_names: Optional[list] = None
    """Names currently being grabbed in continuous mode."""

    pub_topic: Optional[str] = None
    """ZMQ publish topic base for the actor's data channel."""

    # State
    last_seen: datetime = field(default_factory=datetime.now)
    reachable: bool = True


@dataclass
class ProxyRecord:
    """One ZMQ PUB/SUB proxy instance."""

    in_port: int
    """Publisher side — actors ``connect`` (or ``bind``) to this port."""

    out_port: int
    """Subscriber side — directors subscribe to this port."""

    label: str = ""
    """User-friendly label, e.g. ``'cameras'``."""

    process: Optional[subprocess.Popen] = None
    """Live process handle when the proxy was started by the manager; ``None`` if external."""

    alive: bool = False
    """``True`` when the proxy process is running (or probed to be running)."""


@dataclass
class CoordinatorRecord:
    """The LECO coordinator."""

    host: str
    port: int
    namespace: Optional[str] = None
    nodes: dict = field(default_factory=dict)
    process: Optional[subprocess.Popen] = None
    alive: bool = False
    log_path: Optional[Path] = None   # path to coordinator stdout/stderr log
    pid_path: Optional[Path] = None   # path to PID file for cross-session management


# ── Monitor ────────────────────────────────────────────────────────────────────

class LECONetworkMonitor:
    """Discovers and manages LECO network components.

    Parameters
    ----------
    component_poll_interval:
        Seconds between fast component-list polls (default 2 s).
    detail_poll_interval:
        Seconds between slow actor-detail polls (default 5 s).
    role_timeout:
        Seconds to wait for a ``get_role()`` RPC response (default 0.3 s).

    Callbacks
    ---------
    Register plain callables on the ``on_*`` attributes before calling
    :meth:`start_polling`.  The GUI layer replaces these with Qt-signal emitters.

    ``on_components_changed(records: list[ComponentRecord])``
        Called whenever the component list changes or is refreshed.
    ``on_actor_details_changed(record: ComponentRecord)``
        Called after actor details (capabilities, topic, …) are fetched.
    ``on_proxy_status_changed(record: ProxyRecord)``
        Called when a proxy is added, removed, or its alive-status changes.
    ``on_coordinator_status_changed(record: CoordinatorRecord)``
        Called when coordinator alive-status changes.
    ``on_nodes_changed(nodes: dict[str, str])``
        Called when the linked coordinator nodes list changes.
    """

    on_components_changed: Callable[[list[ComponentRecord]], None]
    on_actor_details_changed: Callable[[ComponentRecord], None]
    on_proxy_status_changed: Callable[[ProxyRecord], None]
    on_coordinator_status_changed: Callable[[CoordinatorRecord], None]
    on_nodes_changed: Callable[[dict], None]

    def __init__(
        self,
        component_poll_interval: float = 2.0,
        detail_poll_interval: float = 5.0,
        role_timeout: float = 0.3,
    ) -> None:
        self._component_poll_interval = component_poll_interval
        self._detail_poll_interval = detail_poll_interval
        self._role_timeout = role_timeout

        self._director: Optional[object] = None  # CoordinatorDirector instance
        self._coordinator_record: Optional[CoordinatorRecord] = None
        self._components: dict[str, ComponentRecord] = {}  # full_name → record
        self._proxies: dict[int, ProxyRecord] = {}         # in_port → record

        self._lock = threading.Lock()

        # Callbacks — default to no-ops
        self.on_components_changed: Callable = lambda records: None
        self.on_actor_details_changed: Callable = lambda record: None
        self.on_proxy_status_changed: Callable = lambda record: None
        self.on_coordinator_status_changed: Callable = lambda record: None
        self.on_nodes_changed: Callable = lambda nodes: None

        # Polling state
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self, host: str = 'localhost', port: int = 12300) -> None:
        """Create a :class:`CoordinatorDirector` and test reachability.

        Parameters
        ----------
        host:
            Coordinator host.
        port:
            Coordinator port.

        Raises
        ------
        ConnectionError
            If the coordinator cannot be reached within the role-timeout.
        """
        from pyleco.directors.coordinator_director import CoordinatorDirector

        record = CoordinatorRecord(host=host, port=port)
        self._coordinator_record = record

        # Attach PID file if one exists from a previous start_coordinator call
        pid_path = Path(tempfile.gettempdir()) / f'leco_coordinator_{port}.pid'
        if pid_path.exists():
            record.pid_path = pid_path

        try:
            self._director = CoordinatorDirector(
                name=f'leco_manager_{os.getpid()}',
                host=host,
                port=port,
            )
            # Probe: try to list components (fast check)
            self._director.get_local_components()
            record.alive = True
        except Exception as exc:
            record.alive = False
            raise ConnectionError(
                f"Cannot reach LECO coordinator at {host}:{port} — {exc}"
            ) from exc
        finally:
            self.on_coordinator_status_changed(record)

    def disconnect(self) -> None:
        """Close the :class:`CoordinatorDirector` ZMQ sockets.

        Marks the coordinator record as not alive and fires the
        ``on_coordinator_status_changed`` callback so the GUI updates immediately.
        Safe to call even when not connected.
        """
        if self._director is not None:
            try:
                self._director.sign_out()
            except Exception:
                logger.debug("disconnect: sign_out failed", exc_info=True)
            try:
                self._director.close()
            except Exception:
                logger.debug("disconnect: close failed", exc_info=True)
            self._director = None

        if self._coordinator_record is not None:
            self._coordinator_record.alive = False
            self.on_coordinator_status_changed(self._coordinator_record)

    def detect_running_managers(self) -> list[str]:
        """Return names of other manager instances already signed in.

        Queries the coordinator for components whose name starts with
        ``leco_manager_``.  Must be called after :meth:`connect`.

        Returns
        -------
        list[str]
            Full component names of any other running managers, e.g.
            ``['leco_manager_1234']``.  Empty list if none found.
        """
        if self._director is None:
            return []
        try:
            names: list[str] = self._director.get_local_components()
        except Exception:
            return []
        my_name = f'leco_manager_{os.getpid()}'
        return [n for n in names if n.startswith('leco_manager_') and n != my_name]

    # ── Component discovery ────────────────────────────────────────────────────

    def refresh_components(self) -> list[ComponentRecord]:
        """Fetch component list from coordinator; classify each via ``get_role()``.

        Tries ``get_global_components()`` first (multi-namespace view), falling
        back to ``get_local_components()`` for older coordinators.

        New names are probed immediately.  Names no longer in the coordinator
        list are marked ``reachable=False`` (stale).

        Returns
        -------
        list[ComponentRecord]
            Current snapshot of all known components.
        """
        if self._director is None:
            return list(self._components.values())

        local_ns = getattr(self._director, '_namespace', None) or 'localhost'

        # Build names_by_ns: prefer global view, fall back to local
        try:
            names_by_ns: dict[str, list[str]] = self._director.get_global_components()
        except (AttributeError, Exception):
            try:
                names: list[str] = self._director.get_local_components()
            except Exception:
                logger.exception("refresh_components: get_local_components() failed")
                return list(self._components.values())
            names_by_ns = {local_ns: names}

        changed = False

        with self._lock:
            # Build the set of full_names currently reported by coordinator
            current_full = set()
            for ns, ns_names in names_by_ns.items():
                for n in ns_names:
                    current_full.add(f'{ns}.{n}')

            known = set(self._components.keys())

            # Mark stale (disappeared from coordinator)
            for gone_full in known - current_full:
                rec = self._components[gone_full]
                if rec.reachable:
                    rec.reachable = False
                    changed = True

            # Classify newly seen components
            for ns, ns_names in names_by_ns.items():
                for n in ns_names:
                    full = f'{ns}.{n}'
                    if full not in self._components:
                        if ns == local_ns:
                            rec = self._probe_component(n)
                        else:
                            rec = ComponentRecord(
                                name=n, full_name=full, role='remote', host=ns
                            )
                        self._components[full] = rec
                        changed = True

            # Refresh last_seen for still-present components
            for full in current_full & known:
                self._components[full].last_seen = datetime.now()
                self._components[full].reachable = True

        records = list(self._components.values())
        if changed:
            self.on_components_changed(records)
        return records

    def _probe_component(self, name: str) -> ComponentRecord:
        """Call ``get_role()`` on *name* and return a :class:`ComponentRecord`."""
        namespace = getattr(self._director, '_namespace', None) or 'localhost'
        full_name = f"{namespace}.{name}"

        try:
            role_info = self._director.ask_rpc(
                method='get_role',
                actor=name,
                timeout=self._role_timeout,
            )
            role = role_info.get('role', 'unknown') if isinstance(role_info, dict) else 'unknown'
            host = role_info.get('host') if isinstance(role_info, dict) else None
        except Exception:
            logger.debug("_probe_component: no reply from '%s' within %.1f s", name, self._role_timeout)
            role = 'unknown'
            host = None

        return ComponentRecord(
            name=name,
            full_name=full_name,
            role=role,
            host=host,
            reachable=(role != 'unknown'),
        )

    # ── Actor detail fetch ─────────────────────────────────────────────────────

    def refresh_actor_details(self, name: str) -> Optional[ComponentRecord]:
        """Fetch capabilities, grabbed_names, and pub_topic for an actor.

        Parameters
        ----------
        name:
            Short component name.

        Returns
        -------
        ComponentRecord or None
            Updated record, or ``None`` if not found / not an actor.
        """
        with self._lock:
            rec = next((r for r in self._components.values() if r.name == name), None)
        if rec is None or rec.role != 'actor':
            return None

        try:
            caps = self._director.ask_rpc(method='get_capabilities', actor=name,
                                          timeout=self._role_timeout)
            rec.capabilities = caps
        except Exception:
            logger.debug("refresh_actor_details: get_capabilities failed for '%s'", name)

        try:
            grabbed = self._director.ask_rpc(method='get_grabbed_names', actor=name,
                                             timeout=self._role_timeout)
            rec.grabbed_names = grabbed
        except Exception:
            pass

        try:
            topic = self._director.ask_rpc(method='get_actor_pub_topic', actor=name,
                                           timeout=self._role_timeout)
            rec.pub_topic = topic
        except Exception:
            pass

        self.on_actor_details_changed(rec)
        return rec

    # ── Component shutdown ─────────────────────────────────────────────────────

    def shutdown_component(self, name: str) -> None:
        """Send ``shutdown`` (actor) or ``disconnect`` (director) RPC to *name*.

        Parameters
        ----------
        name:
            Short component name.
        """
        with self._lock:
            rec = next((r for r in self._components.values() if r.name == name), None)
        if rec is None:
            logger.warning("shutdown_component: '%s' not found in registry", name)
            return

        if rec.role == 'actor':
            method = 'shutdown'
        elif rec.role == 'director':
            method = 'disconnect'
        else:
            # Unknown / coordinator — remove from local display only
            with self._lock:
                self._components.pop(rec.full_name, None)
            self.on_components_changed(list(self._components.values()))
            return

        try:
            self._director.ask_rpc(method=method, actor=name, timeout=1.0)
        except Exception:
            logger.debug("shutdown_component: RPC '%s' to '%s' failed (may already be gone)",
                         method, name)
        # Remove from local registry; coordinator will unregister the component
        with self._lock:
            self._components.pop(rec.full_name, None)
        self.on_components_changed(list(self._components.values()))

    # ── Coordinator lifecycle ──────────────────────────────────────────────────

    def start_coordinator(
        self,
        host: str = 'localhost',
        port: int = 12300,
        namespace: Optional[str] = None,
    ) -> CoordinatorRecord:
        """Launch a coordinator subprocess, detached from the GUI process group.

        The coordinator's stdout/stderr is redirected to a temp log file.
        A PID file is written so that a later GUI session can clean up if needed.

        Parameters
        ----------
        host:
            Bind host for the coordinator (informational; passed to the process
            via ``--host``).
        port:
            Port to listen on.
        namespace:
            Optional LECO namespace.

        Returns
        -------
        CoordinatorRecord
            Record with ``alive=True`` once the coordinator is ready.
        """
        log_path = Path(tempfile.gettempdir()) / f'leco_coordinator_{port}.log'
        pid_path = Path(tempfile.gettempdir()) / f'leco_coordinator_{port}.pid'

        cmd = [sys.executable, '-m', 'pyleco.coordinators.coordinator',
               '--port', str(port)]
        if namespace:
            cmd += ['--namespace', namespace]

        log_file = open(log_path, 'w')
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,   # detach from GUI process group
        )
        log_file.close()  # coordinator holds its own fd; GUI reads separately
        pid_path.write_text(str(proc.pid))

        record = CoordinatorRecord(
            host=host,
            port=port,
            namespace=namespace,
            process=proc,
            alive=False,
            log_path=log_path,
            pid_path=pid_path,
        )
        self._coordinator_record = record
        self.on_coordinator_status_changed(record)

        # Wait for coordinator to be ready (up to 3 s)
        self._await_coordinator_ready(host, port, record)
        return record

    def _await_coordinator_ready(
        self,
        host: str,
        port: int,
        record: CoordinatorRecord,
        retries: int = 15,
        interval: float = 0.2,
    ) -> None:
        """Poll until coordinator responds to pong() or retries exhausted."""
        from pyleco.directors.coordinator_director import CoordinatorDirector
        for _ in range(retries):
            time.sleep(interval)
            try:
                d = CoordinatorDirector(
                    name=f'leco_probe_{os.getpid()}',
                    host=host,
                    port=port,
                )
                d.ask_rpc(method='pong', timeout=0.3)
                d.close()
                record.alive = True
                self.on_coordinator_status_changed(record)
                return
            except Exception:
                pass
        logger.warning(
            "start_coordinator: coordinator did not become ready within %.1f s",
            retries * interval,
        )

    def stop_coordinator(self) -> None:
        """Terminate the coordinator process gracefully.

        Order of attempts:
        1. Graceful: LECO ``shut_down_actor`` RPC via the director.
        2. SIGTERM the process if this manager owns it.
        3. PID file fallback for coordinators started by a previous GUI session.
        """
        rec = self._coordinator_record
        if rec is None:
            return

        # 1. Graceful: LECO shut_down RPC (works with or without a process handle)
        if self._director is not None:
            try:
                self._director.shut_down_actor()
            except Exception:
                logger.debug("stop_coordinator: shut_down_actor RPC failed", exc_info=True)

        # 2. SIGTERM the process if we own it
        if rec.process is not None:
            rec.process.terminate()
            try:
                rec.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                rec.process.kill()

        # 3. PID file fallback (GUI was restarted, coordinator survived)
        elif rec.pid_path is not None and rec.pid_path.exists():
            try:
                pid = int(rec.pid_path.read_text().strip())
                os.kill(pid, signal.SIGTERM)
            except (ValueError, ProcessLookupError, PermissionError):
                pass

        # Cleanup
        if rec.pid_path is not None:
            rec.pid_path.unlink(missing_ok=True)
        rec.alive = False
        self.on_coordinator_status_changed(rec)

    # ── Proxy lifecycle ────────────────────────────────────────────────────────

    def add_proxy(
        self,
        in_port: int,
        out_port: int,
        label: str = '',
    ) -> ProxyRecord:
        """Launch a ZMQ PUB/SUB proxy subprocess.

        Parameters
        ----------
        in_port:
            Publisher side (actors publish here).
        out_port:
            Subscriber side (directors subscribe here).
        label:
            User-friendly label.

        Returns
        -------
        ProxyRecord
        """
        try:
            from pyleco.core import PROXY_RECEIVING_PORT, PROXY_SENDING_PORT
            use_default_module = (
                in_port == PROXY_RECEIVING_PORT and out_port == PROXY_SENDING_PORT
            )
        except ImportError:
            use_default_module = False

        if use_default_module:
            cmd = [sys.executable, '-m', 'pyleco.coordinators.proxy_server']
        else:
            cmd = [sys.executable, '-c',
                   f'import zmq; ctx=zmq.Context(); '
                   f'f=ctx.socket(zmq.XSUB); f.bind("tcp://*:{in_port}"); '
                   f'b=ctx.socket(zmq.XPUB); b.bind("tcp://*:{out_port}"); '
                   f'zmq.proxy(f, b)']

        proc = subprocess.Popen(cmd, start_new_session=True)
        record = ProxyRecord(
            in_port=in_port,
            out_port=out_port,
            label=label,
            process=proc,
            alive=True,
        )
        with self._lock:
            self._proxies[in_port] = record
        self.on_proxy_status_changed(record)
        return record

    def remove_proxy(self, in_port: int) -> None:
        """Stop and remove a proxy.

        For owned proxies the process is terminated.  External proxies (no
        ``process``) are simply removed from the registry.

        Parameters
        ----------
        in_port:
            Publisher-side port identifying the proxy.
        """
        with self._lock:
            rec = self._proxies.pop(in_port, None)
        if rec is None:
            return
        if rec.process is not None:
            rec.process.terminate()
            try:
                rec.process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                rec.process.kill()
        rec.alive = False
        self.on_proxy_status_changed(rec)

    def probe_proxy(self, in_port: int, out_port: int) -> bool:
        """Check if a proxy is alive.

        For proxies owned by this manager, uses ``process.poll()``.
        External proxies (no process handle) are always reported as
        ``"unmonitored"`` (returns ``False`` — manager cannot verify).

        Parameters
        ----------
        in_port:
            Publisher-side port.
        out_port:
            Subscriber-side port (unused for owned proxies; reserved for future
            ZMQ-level probing of external proxies).

        Returns
        -------
        bool
            ``True`` if the proxy process is running.
        """
        with self._lock:
            rec = self._proxies.get(in_port)
        if rec is None:
            return False
        if rec.process is not None:
            alive = rec.process.poll() is None
            if rec.alive != alive:
                rec.alive = alive
                self.on_proxy_status_changed(rec)
            return alive
        # External proxy — cannot monitor; leave alive-state unchanged
        return False

    # ── Nodes ──────────────────────────────────────────────────────────────────

    def refresh_nodes(self) -> dict:
        """Fetch linked coordinator nodes. Fires ``on_nodes_changed``.

        Returns
        -------
        dict[str, str]
            Mapping of namespace → ``"host:port"`` for each linked node.
            Empty dict if not connected or on error.
        """
        if self._director is None:
            return {}
        try:
            nodes = self._director.get_nodes()   # {namespace: "host:port"}
        except Exception:
            logger.debug("refresh_nodes: get_nodes() failed", exc_info=True)
            return {}
        if self._coordinator_record is not None:
            self._coordinator_record.nodes = nodes
        self.on_nodes_changed(nodes)
        return nodes

    # ── Health checks ──────────────────────────────────────────────────────────

    def _check_coordinator_health(self) -> None:
        """Check if the coordinator is still alive; fire callback on state change."""
        rec = self._coordinator_record
        if rec is None:
            return

        alive = False
        # Check process exit code if we own it
        if rec.process is not None and rec.process.poll() is not None:
            alive = False
        elif self._director is not None:
            try:
                self._director.ask_rpc(method='pong', timeout=self._role_timeout)
                alive = True
            except Exception:
                alive = False
        else:
            return  # no director, no process — nothing to check

        if alive != rec.alive:
            rec.alive = alive
            self.on_coordinator_status_changed(rec)

    def _check_proxies_health(self) -> None:
        """Probe all managed proxies."""
        with self._lock:
            proxies = list(self._proxies.items())
        for in_port, rec in proxies:
            self.probe_proxy(in_port, rec.out_port)

    # ── Two-tier polling loop ──────────────────────────────────────────────────

    def start_polling(self) -> None:
        """Start the background polling thread.

        Fast tier (``component_poll_interval``): refresh component list.
        Slow tier (``detail_poll_interval``): refresh actor details.

        Safe to call multiple times; a second call is a no-op if already running.
        """
        if self._poll_thread is not None and self._poll_thread.is_alive():
            return
        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name='leco-monitor-poll',
        )
        self._poll_thread.start()

    def stop_polling(self) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=max(self._component_poll_interval * 2, 5.0))
        self._poll_thread = None

    def _poll_loop(self) -> None:
        """Background thread: fast + slow poll tiers."""
        last_detail_time = 0.0
        while not self._stop_event.is_set():
            t0 = time.monotonic()

            # Fast tier: component list + health checks
            self.refresh_components()
            self._check_coordinator_health()
            self._check_proxies_health()

            # Slow tier: actor details + nodes
            if t0 - last_detail_time >= self._detail_poll_interval:
                last_detail_time = t0
                with self._lock:
                    actor_short_names = [
                        r.name for r in self._components.values() if r.role == 'actor'
                    ]
                for name in actor_short_names:
                    if self._stop_event.is_set():
                        break
                    self.refresh_actor_details(name)
                self.refresh_nodes()

            # Sleep until next fast tick
            elapsed = time.monotonic() - t0
            remaining = self._component_poll_interval - elapsed
            if remaining > 0:
                self._stop_event.wait(timeout=remaining)

    # ── Accessors ──────────────────────────────────────────────────────────────

    @property
    def components(self) -> list[ComponentRecord]:
        """Current component snapshot (thread-safe copy)."""
        with self._lock:
            return list(self._components.values())

    @property
    def proxies(self) -> list[ProxyRecord]:
        """Current proxy list (thread-safe copy)."""
        with self._lock:
            return list(self._proxies.values())

    @property
    def coordinator(self) -> Optional[CoordinatorRecord]:
        """Current coordinator record."""
        return self._coordinator_record
