"""Hardware plugin registry for the PymodaqActor GUI.

Hardware classes are discovered via the ``pymodaq.hardware`` entry point group.
Plugin packages declare pure hardware classes (no DAQ wrapper required)::

    # In a plugin package's pyproject.toml
    [project.entry-points."pymodaq.hardware"]
    MockStage = "pymodaq_plugins_mock.hardware.mock_stage:MockStageDevice"

If no entry points are registered the registry is empty and the instrument list
in the GUI will be empty with a suitable status-bar message.
"""
from __future__ import annotations

import logging
from importlib.metadata import entry_points

logger = logging.getLogger(__name__)


def get_hardware_registry() -> list[dict]:
    """Return ``[{name, cls, capabilities}]`` from ``pymodaq.hardware`` entry points.

    Each entry has:
    - ``name``         — entry-point name (display label)
    - ``cls``          — hardware class (implements actor device interface)
    - ``capabilities`` — :class:`~pymodaq.control_modules.capabilities.Capabilities`
                         (from class attribute or inferred via ``infer_capabilities``)
    """
    from pymodaq.control_modules.capabilities import Capabilities, infer_capabilities

    result: list[dict] = []
    for ep in entry_points(group='pymodaq.hardware'):
        try:
            cls = ep.load()
            caps = getattr(cls, 'capabilities', None)
            if caps is None:
                caps = infer_capabilities(cls())
            result.append({'name': ep.name, 'cls': cls, 'capabilities': caps})
        except Exception as exc:
            logger.warning("Could not load hardware entry point %r: %s", ep.name, exc)
    return result


# Module-level registry (loaded once at import; empty if no hardware registered)
HARDWARE_REGISTRY: list[dict] = get_hardware_registry()
HARDWARE_NAMES: list[str] = [e['name'] for e in HARDWARE_REGISTRY]
