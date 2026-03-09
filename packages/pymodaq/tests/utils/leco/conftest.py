"""Conftest for leco actor tests.

Loads actor.py, capabilities.py, rpc_method_definitions.py, director_utils.py
and actor_gui.py directly from their source paths, bypassing the Qt-laden
pymodaq/__init__.py chain.
All other pymodaq sub-packages are stubbed as MagicMock so normal import
statements in test files resolve without triggering Qt.
"""
import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ── Headless Qt display ────────────────────────────────────────────────────────
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


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


def _stub_module_with(name: str, **attrs) -> types.ModuleType:
    """Register a simple module stub with given attributes."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


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

# ── Step 3: stubs for actor_gui.py dependencies ───────────────────────────────
# ThreadCommand: minimal stub (command + attribute, no serialisation needed)
class _ThreadCommand:
    def __init__(self, command, attribute=None, args=(), kwargs=None):
        self.command = command
        self.attribute = attribute
        self.args = args
        self.kwargs = kwargs or {}

    def __repr__(self):
        return f'ThreadCommand({self.command!r}, {self.attribute!r})'


if 'pymodaq_utils.utils' not in sys.modules:
    _stub_module_with('pymodaq_utils.utils', ThreadCommand=_ThreadCommand)
else:
    # Already loaded — patch ThreadCommand if it's not the real one
    _utils_mod = sys.modules['pymodaq_utils.utils']
    if not hasattr(_utils_mod, 'ThreadCommand'):
        _utils_mod.ThreadCommand = _ThreadCommand


# CustomApp stub — must be a real class so PymodaqActorGUI can inherit from it
class _CustomApp:
    """Minimal stub for pymodaq_gui.utils.custom_app.CustomApp."""

    def __init__(self, parent=None, title='', **kwargs):
        self.docks = {}
        self._actions = {}
        self._statusbar = MagicMock()
        self._statusbar.showMessage = MagicMock()
        if hasattr(self, 'params'):
            self.settings = _ParamStub(self.params)
        else:
            self.settings = _ParamStub([])
        self.settings_tree = MagicMock()
        self.dockarea = parent if parent is not None else MagicMock()

    def setup_ui(self):
        self.setup_docks()
        self.setup_actions()
        self.connect_things()

    def setup_docks(self): pass
    def setup_actions(self): pass
    def connect_things(self): pass
    def value_changed(self, param): pass

    def add_action(self, name, *args, enabled=True, **kwargs):
        act = MagicMock()
        act.isEnabled.return_value = enabled
        act.setEnabled = lambda v: act.isEnabled.return_value.__class__  # noop
        self._actions[name] = act

    def get_action(self, name):
        if name not in self._actions:
            self.add_action(name)
        return self._actions[name]

    @property
    def statusbar(self):
        return self._statusbar


class _ParamStub:
    """Ultra-minimal Parameter stub supporting child() and [] access."""

    def __init__(self, spec):
        self._spec = spec
        self._values = {}
        self._children = {}
        for item in spec:
            name = item.get('name', '')
            val = item.get('value', item.get('limits', [None])[0] if item.get('limits') else None)
            self._values[name] = val
            if 'children' in item:
                self._children[name] = _ParamStub(item['children'])

    def child(self, *path):
        node = self
        for key in path:
            node = node._children.get(key, _ParamChildStub(key))
        return node

    def __getitem__(self, key):
        return self._values.get(key)

    def setLimits(self, limits): pass
    def setValue(self, val): pass
    def saveState(self): return {}
    def opts(self): return {}


class _ParamChildStub:
    def __init__(self, name):
        self._name = name
        self._val = None

    def child(self, *path):
        return _ParamChildStub('.'.join(path))

    def setValue(self, val):
        self._val = val

    def value(self):
        return self._val

    def opts(self):
        return {}

    def setLimits(self, limits): pass
    def name(self): return self._name


# Register GUI stubs as real modules with real classes
_stub_module_with(
    'pymodaq_gui.utils.custom_app',
    CustomApp=_CustomApp,
)
_stub_module_with(
    'pymodaq_gui.qt_utils',
    mkQApp=MagicMock(return_value=MagicMock()),
)
_stub_module_with(
    'pymodaq_gui.utils.dock',
    Dock=type('Dock', (), {
        '__init__': lambda self, *a, **k: None,
        'addWidget': lambda self, *a, **k: None,
        'hide': lambda self: None,
        'show': lambda self: None,
    }),
    DockArea=type('DockArea', (), {
        '__init__': lambda self, *a, **k: None,
        'addDock': lambda self, *a, **k: None,
    }),
)

# QLED stub — must support set_as() and .state
class _QLED:
    def __init__(self, *args, **kwargs):
        self.state = False

    def set_as(self, val):
        self.state = bool(val)

_stub_module_with(
    'pymodaq_gui.utils.widgets.qled',
    QLED=_QLED,
)
# Also make the parent package attribute accessible
if 'pymodaq_gui.utils.widgets' not in sys.modules:
    _stub_package('pymodaq_gui.utils.widgets')
if 'pymodaq_gui.utils' not in sys.modules:
    _stub_package('pymodaq_gui.utils')

# Parameter / ParameterTree stubs for pymodaq_gui.parameter
_stub_module_with(
    'pymodaq_gui.parameter',
    Parameter=type('Parameter', (), {
        'create': staticmethod(lambda name='', type='group', children=None, **kw:
            _ParameterGroupStub(name, children or [])),
    }),
    ParameterTree=type('ParameterTree', (), {
        '__init__': lambda self, *a, **k: None,
        'setParameters': lambda self, *a, **k: None,
        'topLevelItemCount': lambda self: 0,
        'topLevelItem': lambda self, i: None,
        'invisibleRootItem': lambda self: None,
    }),
)


class _ParameterGroupStub:
    """Minimal Parameter.create() result supporting child() and signal connections."""

    def __init__(self, name, children):
        self._name = name
        self._children = {}
        for c in children:
            child_name = c.get('name', '')
            if c.get('type') == 'group':
                self._children[child_name] = _ParameterGroupStub(child_name, c.get('children', []))
            else:
                self._children[child_name] = _ParameterLeafStub(child_name, c.get('type', 'str'))

    def child(self, *path):
        node = self
        for key in path:
            node = node._children.get(key, _ParameterLeafStub(key, 'str'))
        return node

    def name(self):
        return self._name


class _ParameterLeafStub:
    def __init__(self, name, ptype):
        self._name = name
        self._type = ptype
        self.sigActivated = _Signal()

    def child(self, *path):
        return _ParameterLeafStub('.'.join(path), 'str')

    def name(self):
        return self._name


class _Signal:
    """Minimal signal stub for sigActivated."""
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in self._slots:
            slot(*args)


# ── Step 4: load actor_gui.py ─────────────────────────────────────────────────
_load_module_from_path(
    'pymodaq.utils.leco.actor_gui',
    _SRC / 'pymodaq' / 'utils' / 'leco' / 'actor_gui.py',
)
