"""Conftest for data_mixer extension tests.

The pymodaq package __init__ (and several sub-packages) eagerly import Qt via
pymodaq_gui.  The tests in this directory only exercise pure-Python logic
(parser, formatters) and don't need a real Qt installation.

This conftest pre-loads the two relevant modules directly from their source
files and registers them in sys.modules under their canonical names, so that
``from pymodaq.extensions.data_mixer.parser import …`` resolves from the
cache without ever triggering the Qt-heavy package initialisers.

Tests that *do* require Qt should use::

    pytest.importorskip("qtpy")

at the top of the test module (or per-test) to skip gracefully when Qt is
absent.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_MIXER_SRC = (
    Path(__file__).parents[2]          # …/packages/pymodaq/
    / "src" / "pymodaq" / "extensions" / "data_mixer"
)


def _stub_package(name: str) -> None:
    """Insert a minimal stub into sys.modules so child imports don't trigger
    the real (Qt-dependent) package __init__."""
    if name not in sys.modules:
        m = types.ModuleType(name)
        m.__path__ = []   # type: ignore[attr-defined]
        m.__spec__ = None  # type: ignore[assignment]
        sys.modules[name] = m


def _load_direct(sys_name: str, rel_path: str):
    """Load *rel_path* (relative to the data_mixer source root) directly and
    register it as *sys_name* in sys.modules."""
    if sys_name in sys.modules:
        return sys.modules[sys_name]
    spec = importlib.util.spec_from_file_location(
        sys_name, _MIXER_SRC / rel_path
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[sys_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ── Bootstrap ──────────────────────────────────────────────────────────────────
# Must run at collection time (before any test module is imported).

for _pkg in (
    "pymodaq",
    "pymodaq.extensions",
    "pymodaq.extensions.data_mixer",
    "pymodaq.extensions.data_mixer.gui",
):
    _stub_package(_pkg)

_load_direct("pymodaq.extensions.data_mixer.parser", "parser.py")
_load_direct("pymodaq.extensions.data_mixer.gui.formatters", "gui/formatters.py")
