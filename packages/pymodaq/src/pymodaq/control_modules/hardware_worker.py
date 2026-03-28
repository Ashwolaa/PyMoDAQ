"""Framework detection helper and unified hardware worker for new-style plugins.

Phase 3 of the capabilities-driven control architecture.

``_is_new_style(plugin)`` detects whether a plugin uses the new
``query_data`` / ``change_to`` interface directly (i.e. it does *not*
rely on the ``DAQ_Move_base`` / ``DAQ_Viewer_base`` adapters).

``DAQ_HardwareWorker`` is a demand-driven per-plugin worker that:

* Serialises all hardware calls to the thread it lives in.
* Provides per-channel ``snap`` / ``grab`` / ``stop`` on top of
  ``query_data``.
* Emits ``data_ready_signal(channel_name, DataToExport)`` so that
  ``ChannelControl`` rows and (Phase 5) ``DAQ_Monitor`` can subscribe
  independently.
* Relays ``change_done_signal`` from the plugin.

Usage
-----
The worker is created inside ``DAQ_Move_Hardware.ini_hardware`` /
``DAQ_Detector.ini_hardware`` after the plugin is instantiated, then
torn down in their ``close()`` methods::

    # inside ini_hardware:
    if _is_new_style(self.plugin):
        self._hw_worker = DAQ_HardwareWorker(self.plugin)

    # inside close():
    if hasattr(self, '_hw_worker'):
        self._hw_worker.close()

Because ``ini_hardware`` is already executing inside the hardware
``QThread``, the ``DAQ_HardwareWorker`` (and its internal ``QTimer``
instances) are automatically affiliated with that thread — no explicit
``moveToThread`` is needed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from qtpy.QtCore import QObject, QTimer, Signal, Slot

if TYPE_CHECKING:
    from pymodaq_data.data import DataToExport
    from pymodaq.control_modules.plugin_base import DAQ_Plugin_base


__all__ = ['_is_new_style', 'DAQ_HardwareWorker']


def _is_new_style(plugin) -> bool:
    """Return ``True`` if *plugin* uses the new-style hardware interface.

    A plugin is considered new-style when it explicitly declares
    ``_new_style_plugin = True`` at the class level *and* inherits
    directly from ``DAQ_Plugin_base`` without going through the
    ``DAQ_Move_base`` / ``DAQ_Viewer_base`` adapters (those override
    the flag back to ``False``).

    Parameters
    ----------
    plugin :
        Any object; returns ``False`` for non-plugin arguments.
    """
    return bool(getattr(plugin, '_new_style_plugin', False))


class DAQ_HardwareWorker(QObject):
    """Per-plugin hardware worker for new-style plugins.

    Provides demand-driven, per-channel acquisition on top of the
    ``query_data`` / ``change_to`` plugin interface.

    All methods are ``@Slot``-decorated so they execute correctly in the
    hardware thread when called via a queued signal.

    Signals
    -------
    data_ready_signal : Signal(str, object)
        Emitted after each successful ``query_data`` call with
        ``(channel_name, DataToExport)``.  Consumers should filter by
        channel name.
    change_done_signal : Signal(str, object)
        Relayed directly from ``plugin.change_done_signal``.

    Parameters
    ----------
    plugin :
        A new-style plugin instance (``_new_style_plugin = True``).
    grab_period_ms :
        Interval in milliseconds between ticks in continuous grab mode.
    """

    data_ready_signal = Signal(str, object)   # (channel_name, DataToExport)
    change_done_signal = Signal(str, object)  # (channel_name, DataToExport | None)

    DEFAULT_GRAB_PERIOD_MS: int = 100

    def __init__(
        self,
        plugin: 'DAQ_Plugin_base',
        grab_period_ms: int = DEFAULT_GRAB_PERIOD_MS,
    ) -> None:
        super().__init__()
        self._plugin = plugin
        self._grab_period_ms = grab_period_ms
        self._cache: dict[str, 'DataToExport'] = {}
        self._grab_timers: dict[str, QTimer] = {}
        # Relay the plugin's change_done_signal transparently.
        plugin.change_done_signal.connect(self.change_done_signal)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def grabbed_names(self) -> set[str]:
        """Channel names currently in an active grab loop."""
        return set(self._grab_timers.keys())

    @Slot(str)
    def snap(self, name: str) -> None:
        """One-shot acquisition for *name*; emits :attr:`data_ready_signal`."""
        dte = self._plugin.query_data(names=[name], fresh=True)
        self._cache[name] = dte
        self.data_ready_signal.emit(name, dte)

    @Slot(str)
    def grab(self, name: str) -> None:
        """Start a continuous grab loop for *name*.

        If a grab loop for *name* is already running this is a no-op.
        """
        if name in self._grab_timers:
            return
        timer = QTimer(self)
        timer.setInterval(self._grab_period_ms)
        timer.timeout.connect(lambda: self._grab_tick(name))
        self._grab_timers[name] = timer
        timer.start()

    @Slot(str)
    def stop(self, name: str) -> None:
        """Stop the grab loop for *name* (no-op if not grabbing)."""
        timer = self._grab_timers.pop(name, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def get_cached(self, name: str) -> Optional['DataToExport']:
        """Return the last acquired value without touching hardware.

        Returns ``None`` if *name* has never been acquired.
        """
        return self._cache.get(name)

    @Slot(str, object)
    def change_to(self, name: str, value) -> None:
        """Apply *value* to channel *name*.

        Delegates to ``plugin.change_to``.  The plugin is responsible
        for emitting ``change_done_signal`` (directly or via
        ``_poll_until_done``) when the operation completes.
        """
        self._plugin.change_to(name, value)

    def close(self) -> None:
        """Stop all grab loops and release resources."""
        for name in list(self._grab_timers.keys()):
            self.stop(name)
        self._cache.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _grab_tick(self, name: str) -> None:
        """Single iteration of the grab loop for *name*."""
        if name not in self._grab_timers:
            return  # stop() was called while tick was pending
        dte = self._plugin.query_data(names=[name], fresh=True)
        self._cache[name] = dte
        self.data_ready_signal.emit(name, dte)
