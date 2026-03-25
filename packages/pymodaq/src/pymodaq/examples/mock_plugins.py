"""Standalone mock plugins for LECO actor/director demos.

Each class implements **two interfaces simultaneously**:

1. The PyMoDAQ hardware-plugin interface (``DAQ_Move_base`` / ``DAQ_Viewer_base``)
   so it can be loaded by the dashboard as a normal instrument plugin.

2. The PymodaqActor device interface (``read(names=None) -> DataToExport``
   and, for move plugins, ``write(name, value) -> None``) so it can be
   wrapped directly by :class:`~pymodaq.utils.leco.actor.PymodaqActor` and
   exercised in headless tests without Qt.

Usage
-----
Dashboard (Qt required):
    Add as instrument plugins in a preset.  Select "LECO Director" as the
    master plugin, point it at the mock actor name, set ``use_legacy_actor = False``.

Headless self-test (no Qt, no network):
    PYTHONPATH=packages/pymodaq_utils/src:packages/pymodaq_data/src:\\
               packages/pymodaq_gui/src:packages/pymodaq/src \\
        python3 packages/pymodaq/src/pymodaq/examples/mock_plugins.py
"""
from __future__ import annotations

# ── Headless bootstrap — stubs Qt-laden imports before pymodaq loads ──────────
# Same pattern as leco_actor_mock.py.  Only activates when a package is NOT
# already in sys.modules, so a normal Qt-enabled import chain is unaffected.
import sys
from pathlib import Path
import importlib.util
from unittest.mock import MagicMock

_SRC = Path(__file__).parents[2]   # packages/pymodaq/src
_UTILS_SRC = Path(__file__).parents[4] / 'pymodaq_utils' / 'src'


def _stub(name: str) -> MagicMock:
    if name not in sys.modules:
        m = MagicMock()
        m.__name__ = name
        m.__path__ = []
        m.__package__ = name
        m.__spec__ = None
        sys.modules[name] = m
    return sys.modules[name]


def _load(canonical: str, rel_path: Path):
    if canonical not in sys.modules:
        spec = importlib.util.spec_from_file_location(canonical, rel_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[canonical] = mod
        spec.loader.exec_module(mod)
    return sys.modules[canonical]


for _pkg in (
    'pymodaq', 'pymodaq.utils', 'pymodaq.utils.leco',
    'pymodaq.control_modules',
    'pymodaq_gui', 'pymodaq_gui.parameter', 'pymodaq_gui.parameter.utils',
    'pymodaq.utils.data', 'pymodaq.utils.leco.utils',
):
    _stub(_pkg)

_load('pymodaq_utils.enums', _UTILS_SRC / 'pymodaq_utils' / 'enums.py')
_load('pymodaq.control_modules.capabilities',
      _SRC / 'pymodaq' / 'control_modules' / 'capabilities.py')
_load('pymodaq.utils.leco.rpc_method_definitions',
      _SRC / 'pymodaq' / 'utils' / 'leco' / 'rpc_method_definitions.py')
_load('pymodaq.utils.leco.actor',
      _SRC / 'pymodaq' / 'utils' / 'leco' / 'actor.py')
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np

from pymodaq.control_modules.capabilities import (
    Capabilities, ContinuousVariable, Observable,
)

class Device:
    """Base class for mock devices."""

    def __init__(self) -> None:            
        self.is_connected = False

    def connect(self):
        self.is_connected = True

    def disconnect(self):
        self.is_connected = False

# ── Qt-independent device-interface layer ─────────────────────────────────────
# These two classes implement the actor device interface only.
# They can be instantiated without Qt / without a DAQ_Move / DAQ_Viewer parent.

class MockStageDevice(Device):
    """Single-axis translation stage — pure Python, no Qt.

    Implements the actor device interface:
      * ``read(names=None)  -> DataToExport``
      * ``write(name, value) -> None``
      * ``capabilities`` class attribute

    Can be wrapped directly by ``PymodaqActor``::

        actor = PymodaqActor('N.stage', MockStageDevice, context=FakeContext())
    """

    capabilities = Capabilities(
        variables=[ContinuousVariable('position', units='mm', lo=-100.0, hi=100.0, epsilon=0.001)],
    )

    def __init__(self) -> None:
        super().__init__()
        self._position: float = 0.0

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        return DataToExport(
            'stage',
            data=[DataRaw('position', data=[np.array([self._position])])],
        )

    def write(self, name: str, value) -> None:
        if name == 'position':
            self._position = float(value)


class MockCameraDevice(Device):
    """Simple 64 × 64 pixel detector — pure Python, no Qt.

    Implements the actor device interface:
      * ``read(names=None) -> DataToExport``
      * ``capabilities`` class attribute
    """
    shape = (2048, 2048)
    shape = (512, 512)
    capabilities = Capabilities(
        observables=[Observable('frame', units='counts', shape=shape, dtype='float32')],
    )

    def __init__(self) -> None:
        super().__init__()
        self._frame_idx: int = 0

    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        self._frame_idx += 1
        frame = np.random.randint(0, 1000, self.shape).astype('float32')
        return DataToExport(
            'camera',
            data=[DataRaw('frame', data=[frame])],
        )


class MockSpectrometerDevice(Device):
    """Mock scanning spectrometer with both a variable and an observable.

    Variables
    ---------
    wavelength : float, nm, [300 … 900]
        Centre wavelength of the grating (actuator axis).
    integration_time : float, ms, [1 … 5000]
        Exposure / integration time.

    Observables
    -----------
    spectrum : float32, shape (256,)
        Simulated spectrum: a Gaussian peak centred at ``wavelength`` with
        amplitude proportional to ``integration_time``.

    This device is the canonical test case for the actor GUI because it
    exercises both DAQ_Move (wavelength, integration_time) and DAQ_Viewer
    (spectrum) directors simultaneously from a single actor.
    """

    N_PIXELS = 256
    _wavelength_axis = np.linspace(300.0, 900.0, N_PIXELS).astype('float32')

    capabilities = Capabilities(
        variables=[
            ContinuousVariable('wavelength',        units='nm', lo=300.0,  hi=900.0,  epsilon=0.1),
            ContinuousVariable('integration_time',  units='ms', lo=1.0,    hi=5000.0, epsilon=0.1),
        ],
        observables=[
            Observable('spectrum', units='counts', shape=(N_PIXELS,), dtype='float32'),
        ],
    )

    def __init__(self) -> None:
        super().__init__()
        self._wavelength: float = 550.0          # nm — grating centre
        self._integration_time: float = 100.0    # ms


    def read(self, names=None):
        from pymodaq_data.data import DataToExport, DataRaw
        data = []

        if names is None or 'wavelength' in names:
            data.append(DataRaw('wavelength', data=[np.array([self._wavelength])]))

        if names is None or 'integration_time' in names:
            data.append(DataRaw('integration_time',
                                data=[np.array([self._integration_time])]))

        if names is None or 'spectrum' in names:
            spectrum = self._make_spectrum()
            data.append(DataRaw('spectrum', data=[spectrum]))

        return DataToExport('spectrometer', data=data)

    def write(self, name: str, value) -> None:
        if name == 'wavelength':
            self._wavelength = float(np.clip(value, 300.0, 900.0))
        elif name == 'integration_time':
            self._integration_time = float(np.clip(value, 1.0, 5000.0))

    def _make_spectrum(self) -> np.ndarray:
        """Gaussian peak at self._wavelength, amplitude ∝ integration_time."""
        amplitude = self._integration_time * 2.0          # counts/ms × 2
        sigma = 20.0                                       # nm FWHM ≈ 47 nm
        spectrum = amplitude * np.exp(
            -0.5 * ((self._wavelength_axis - self._wavelength) / sigma) ** 2
        )
        noise = np.random.normal(0.0, max(1.0, amplitude * 0.01),
                                 self.N_PIXELS).astype('float32')
        return (spectrum + noise).astype('float32')


# ── Qt-dependent plugin wrappers ───────────────────────────────────────────────
# Import DAQ_Move_base / DAQ_Viewer_base only if Qt is available.

try:
    from pymodaq_data.data import DataToExport, DataRaw
    from pymodaq.control_modules.move_utility_classes import (
        DAQ_Move_base, comon_parameters_fun, main as move_main,
        DataActuator, DataActuatorType,
    )
    from pymodaq.control_modules.viewer_utility_classes import (
        DAQ_Viewer_base, comon_parameters, main as viewer_main,
    )
    from pymodaq_utils.utils import ThreadCommand
    from pymodaq.utils.data import DataFromPlugins

    _QT_AVAILABLE = True

except (ImportError, Exception):
    _QT_AVAILABLE = False


if _QT_AVAILABLE:

    class DAQ_Move_MockStage(DAQ_Move_base):
        """Mock actuator plugin — wraps ``MockStageDevice``.

        Implements both:
        * ``DAQ_Move_base`` (full PyMoDAQ plugin interface)
        * Actor device interface (``read`` / ``write`` + ``capabilities``)
        """

        _axis_names = ['position']
        _controller_units = 'mm'
        _epsilon = 0.001
        data_actuator_type = DataActuatorType.DataActuator

        params = comon_parameters_fun(axis_names=_axis_names, epsilon=_epsilon)

        # Actor device interface
        capabilities = MockStageDevice.capabilities

        def read(self, names=None) -> DataToExport:
            return self.controller.read(names=names)

        def write(self, name: str, value) -> None:
            self.controller.write(name, value)

        # DAQ_Move_base interface

        def ini_stage(self, controller=None):
            if self.is_master:
                self.controller = MockStageDevice()
            else:
                self.controller = controller
            return 'MockStage initialized', True

        def move_abs(self, position: DataActuator) -> None:
            position = self.check_bound(position)
            position = self.set_position_with_scaling(position)
            self.target_value = position
            self.controller.write('position', position.value(self.axis_unit))

        def move_rel(self, position: DataActuator) -> None:
            current = self.controller._position
            target = current + position.value(self.axis_unit)
            abs_pos = DataActuator(data=[np.atleast_1d(np.array([target]))])
            self.move_abs(abs_pos)

        def move_home(self) -> None:
            self.move_abs(DataActuator(data=[np.atleast_1d(np.array([0.0]))]))

        def get_actuator_value(self) -> DataActuator:
            pos_val = self.controller._position
            return DataActuator(data=[np.atleast_1d(np.array([pos_val]))])

        def stop_motion(self) -> None:
            pass

        def close(self) -> None:
            self.controller = None


    class DAQ_0DViewer_MockCamera(DAQ_Viewer_base):
        """Mock 0-D detector plugin — wraps ``MockCameraDevice``.

        Returns the mean of the 64×64 frame as a scalar so the dashboard sees
        it as a 0-D channel.

        Implements both:
        * ``DAQ_Viewer_base`` (full PyMoDAQ plugin interface)
        * Actor device interface (``read`` + ``capabilities``)
        """

        params = comon_parameters

        # Actor device interface
        capabilities = MockCameraDevice.capabilities

        def read(self, names=None) -> DataToExport:
            return self.controller.read(names=names)

        # DAQ_Viewer_base interface

        def ini_detector(self, controller=None):
            if self.is_master:
                self.controller = MockCameraDevice()
            else:
                self.controller = controller
            return 'MockCamera initialized', True

        def grab_data(self, Naverage=1, **kwargs):
            dte = self.controller.read()
            frame = dte.data[0].data[0]          # shape (64, 64)
            scalar = np.array([frame.mean()])
            dfp = DataFromPlugins('MockCamera', data=[scalar])
            self.dte_signal.emit(DataToExport('camera', data=[dfp]))

        def stop(self) -> None:
            pass

        def close(self) -> None:
            self.controller = None


# ── Self-test (headless — no Qt, no network) ──────────────────────────────────

def _self_test() -> None:
    """Smoke test exercisable without Qt or a LECO network."""
    import json
    from pyleco.test import FakeContext, handle_request_message
    from serializall import SerializableFactory
    from pymodaq.utils.leco.actor import PymodaqActor

    def rpc_result(actor):
        frames = actor.socket._s[-1]
        for frame in frames:
            try:
                parsed = json.loads(frame.decode())
                if isinstance(parsed, dict) and 'result' in parsed:
                    return parsed['result']
            except Exception:
                continue
        raise AssertionError('No RPC result found')

    print('── MockStageDevice via PymodaqActor ──')
    actor = PymodaqActor('N.stage', MockStageDevice, context=FakeContext())
    actor.connect()

    handle_request_message(actor, 'change_to', name='position', value=42.0)
    assert actor.device._position == 42.0, 'write failed'

    handle_request_message(actor, 'query_data', names=None, fresh=True)
    # _publish now sends one frame per DWA on sub-topic "{full_name}/{dwa_name}".
    # Find the frame for the 'position' channel.
    pos_frame = next(
        f for f in actor.publisher.socket._s
        if (f[0].decode() if isinstance(f[0], bytes) else f[0]).endswith('/position')
    )
    dte = SerializableFactory().get_apply_deserializer(pos_frame[2])
    assert dte.data[0].name == 'position', f'unexpected DWA name: {dte.data[0].name}'
    val = float(dte.data[0].data[0].ravel()[0])
    assert val == 42.0, f'expected 42.0 got {val}'
    print('  MockStageDevice: change_to + query_data  ✓')

    handle_request_message(actor, 'get_capabilities')
    caps = Capabilities.from_dict(rpc_result(actor))
    assert caps.variables[0].name == 'position'
    print('  MockStageDevice: get_capabilities  ✓')

    print('── MockCameraDevice via PymodaqActor ──')
    actor2 = PymodaqActor('N.cam', MockCameraDevice, context=FakeContext())
    actor2.connect()

    handle_request_message(actor2, 'query_data', names=None, fresh=True)
    # Find the frame for the 'frame' channel.
    frame_frame = next(
        f for f in actor2.publisher.socket._s
        if (f[0].decode() if isinstance(f[0], bytes) else f[0]).endswith('/frame')
    )
    dte2 = SerializableFactory().get_apply_deserializer(frame_frame[2])
    assert dte2.data[0].name == 'frame'
    assert dte2.data[0].data[0].shape == MockCameraDevice.shape
    print('  MockCameraDevice: query_data + shape check  ✓')

    handle_request_message(actor2, 'get_capabilities')
    caps2 = Capabilities.from_dict(rpc_result(actor2))
    assert caps2.observables[0].name == 'frame'
    print('  MockCameraDevice: get_capabilities  ✓')

    print('\nAll self-tests passed.')


if __name__ == '__main__':
    _self_test()
