"""Conftest for control_modules tests.

Pre-loads pure-Python modules (capabilities.py) directly from their file path,
bypassing pymodaq/__init__.py and pymodaq/control_modules/__init__.py which both
require Qt.  The loaded modules are registered in sys.modules under their canonical
names so that normal import statements in test files resolve to the real objects.

This conftest intentionally does NOT import pymodaq itself; tests that need the full
Qt-enabled pymodaq package must be run in an environment with a Qt binding installed.
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock


def _load_module_from_path(canonical_name: str, file_path: Path):
    """Load a .py file directly and register it in sys.modules."""
    spec = importlib.util.spec_from_file_location(canonical_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[canonical_name] = module
    spec.loader.exec_module(module)
    return module


def _stub_package(name: str) -> MagicMock:
    """Register a MagicMock as a package stub in sys.modules."""
    mock = MagicMock()
    mock.__name__ = name
    mock.__path__ = []
    mock.__package__ = name
    mock.__spec__ = None
    sys.modules[name] = mock
    return mock


# Root of the pymodaq source tree (packages/pymodaq/src/)
# __file__ is packages/pymodaq/tests/control_modules/conftest.py
# parents[0] = control_modules, [1] = tests, [2] = pymodaq, [3] = packages
_SRC = Path(__file__).parents[2] / 'src'

# ── Step 1: stub parent packages so that dotted imports don't trigger __init__ ──
# Only stub if not already in sys.modules (don't clobber a real Qt import).
for _pkg in ('pymodaq', 'pymodaq.control_modules'):
    if _pkg not in sys.modules:
        _stub_package(_pkg)

# ── Step 2: load pure-Python modules directly from their source files ─────────
_load_module_from_path(
    'pymodaq.control_modules.capabilities',
    _SRC / 'pymodaq' / 'control_modules' / 'capabilities.py',
)
