"""Conftest for leco actor tests.

Loads actor.py, capabilities.py, rpc_method_definitions.py and director_utils.py
directly from their source paths, bypassing the Qt-laden pymodaq/__init__.py chain.
All other pymodaq sub-packages are stubbed as MagicMock so normal import statements
in test files resolve without triggering Qt.
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


# ── Paths (cross-platform, relative to this file) ─────────────────────────────
# __file__ = packages/pymodaq/tests/utils/leco/conftest.py
# parents[3] = packages/pymodaq/   parents[4] = packages/
_SRC = Path(__file__).parents[3] / 'src'
_UTILS_SRC = Path(__file__).parents[4] / 'pymodaq_utils' / 'src'

# ── Step 1: stub parent packages to prevent __init__ from loading Qt ───────────
for _pkg in (
    'pymodaq', 'pymodaq.control_modules', 'pymodaq.utils', 'pymodaq.utils.leco',
    'pymodaq_gui', 'pymodaq_gui.parameter', 'pymodaq_gui.parameter.utils',
    'pymodaq.utils.data', 'pymodaq.utils.leco.utils',
):
    if _pkg not in sys.modules:
        _stub_package(_pkg)

# ── Step 2: load pure-Python modules directly ──────────────────────────────────
_load_module_from_path(
    'pymodaq_utils.enums',
    _UTILS_SRC / 'pymodaq_utils' / 'enums.py',
)
_load_module_from_path(
    'pymodaq.control_modules.capabilities',
    _SRC / 'pymodaq' / 'control_modules' / 'capabilities.py',
)
_load_module_from_path(
    'pymodaq.utils.leco.actor',
    _SRC / 'pymodaq' / 'utils' / 'leco' / 'actor.py',
)
_load_module_from_path(
    'pymodaq.utils.leco.rpc_method_definitions',
    _SRC / 'pymodaq' / 'utils' / 'leco' / 'rpc_method_definitions.py',
)
_load_module_from_path(
    'pymodaq.utils.leco.director_utils',
    _SRC / 'pymodaq' / 'utils' / 'leco' / 'director_utils.py',
)
