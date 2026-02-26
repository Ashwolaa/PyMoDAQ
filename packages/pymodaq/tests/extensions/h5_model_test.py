"""Tests for DataMixerModelH5.

Qt-dependent parts (QTimer, autocomplete wiring) are not exercised here.
We test:
  - model discovery via get_models()
  - formula compilation + evaluation (_compute_formula)
  - H5 round-trip: write with DataSaverLoader, load with DataLoader
  - compute() end-to-end with a real H5 file and mocked Qt surface
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from pymodaq_data.data import DataToExport, DataWithAxes, DataSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_dwa(name: str, array: np.ndarray) -> DataWithAxes:
    return DataWithAxes(name, source=DataSource['raw'], data=[array])


def make_dte(name: str, **kwargs) -> DataToExport:
    """Build a DataToExport from keyword (dwa_name=array) pairs."""
    dwas = [make_dwa(k, v) for k, v in kwargs.items()]
    return DataToExport(name, data=dwas)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_data_mixer():
    """Minimal mock that satisfies DataMixerModel.__init__."""
    dm = MagicMock()
    return dm


@pytest.fixture
def h5_model(mock_data_mixer):
    """DataMixerModelH5 instantiated without calling ini_model (avoids QTimer)."""
    from pymodaq.extensions.data_mixer.models.h5_model import DataMixerModelH5
    model = DataMixerModelH5(mock_data_mixer)
    # Manually set the attributes that ini_model() would create
    model._h5saver_low = None
    model._h5_data_names = []
    return model


@pytest.fixture
def h5_file(tmp_path):
    """Write a small H5 scan file and return its Path.

    Uses the same DataSaverLoader / H5SaverLowLevel pattern as DAQScan.
    """
    from pymodaq_data.h5modules.saving import H5SaverLowLevel
    from pymodaq_data.h5modules.data_saving import DataSaverLoader

    file_path = tmp_path / 'scan.h5'
    arr = np.linspace(0.0, 9.0, 10)
    dwa = make_dwa('channel00', arr)

    writer = H5SaverLowLevel()
    writer.init_file(file_name=file_path, new_file=True)
    DataSaverLoader(writer).add_data('/RawData', dwa)
    writer.close_file()
    return file_path


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestDataMixerModelH5Discovery:

    def test_h5_model_present_in_get_models(self):
        from pymodaq.extensions.data_mixer.model import get_models
        models = get_models()
        class_names = [m['class'].__name__ for m in models]
        assert 'DataMixerModelH5' in class_names

    def test_base_class_is_data_mixer_model(self):
        """The klass.__base__ is DataMixerModel check in get_models must pass."""
        from pymodaq.extensions.data_mixer.model import DataMixerModel
        from pymodaq.extensions.data_mixer.models.h5_model import DataMixerModelH5
        assert DataMixerModelH5.__base__ is DataMixerModel

    def test_h5_model_has_params(self):
        from pymodaq.extensions.data_mixer.models.h5_model import DataMixerModelH5
        param_names = [p['name'] for p in DataMixerModelH5.params]
        assert 'h5_file' in param_names
        assert 'edit_formula' in param_names
        assert 'compute' in param_names
        assert 'live_scan' in param_names


# ---------------------------------------------------------------------------
# _compute_formula (pure logic, no H5 or Qt)
# ---------------------------------------------------------------------------

class TestComputeFormula:

    def test_scalar_multiply(self, h5_model):
        arr = np.array([1.0, 2.0, 3.0])
        dte = make_dte('test', channel=arr)
        result = h5_model._compute_formula('{channel} * 2', dte, 'doubled')
        np.testing.assert_allclose(result.data[0], arr * 2)

    def test_numpy_constant_available(self, h5_model):
        # np is in scope — verify by multiplying with np.pi (a float constant)
        arr = np.array([1.0, 2.0, 3.0])
        dte = make_dte('test', channel=arr)
        result = h5_model._compute_formula('{channel} * np.pi', dte, 'pi_scaled')
        np.testing.assert_allclose(result.data[0], arr * np.pi)

    def test_output_name_is_set(self, h5_model):
        arr = np.zeros(5)
        dte = make_dte('test', channel=arr)
        result = h5_model._compute_formula('{channel}', dte, 'my_output')
        assert result.name == 'my_output'

    def test_two_operands(self, h5_model):
        a = np.array([1.0, 2.0])
        b = np.array([3.0, 4.0])
        dte = make_dte('test', sig_a=a, sig_b=b)
        result = h5_model._compute_formula('{sig_a} + {sig_b}', dte, 'sum')
        np.testing.assert_allclose(result.data[0], a + b)

    def test_cross_reference_between_formulas(self, h5_model):
        """Result of formula A can be used as input to formula B."""
        arr = np.array([2.0, 4.0, 6.0])
        dte = make_dte('test', raw=arr)

        dwa_a = h5_model._compute_formula('{raw} * 2', dte, 'a')
        dte_ext = DataToExport('ext', data=list(dte.data) + [dwa_a])
        dwa_b = h5_model._compute_formula('{a} + 1', dte_ext, 'b')

        np.testing.assert_allclose(dwa_a.data[0], arr * 2)
        np.testing.assert_allclose(dwa_b.data[0], arr * 2 + 1)

    def test_formula_with_numpy_constant(self, h5_model):
        arr = np.zeros(4)
        dte = make_dte('test', ch=arr)
        result = h5_model._compute_formula('{ch} + np.pi', dte, 'pi_offset')
        np.testing.assert_allclose(result.data[0], np.pi)


# ---------------------------------------------------------------------------
# H5 file management helpers
# ---------------------------------------------------------------------------

class TestH5FileHelpers:

    def test_open_and_close_h5(self, h5_model, h5_file):
        h5_model._open_h5(h5_file)
        assert h5_model._h5saver_low is not None
        assert h5_model._h5saver_low.isopen()
        h5_model._close_h5()
        assert h5_model._h5saver_low is None

    def test_close_h5_when_already_none_is_safe(self, h5_model):
        assert h5_model._h5saver_low is None
        h5_model._close_h5()   # must not raise

    def test_refresh_h5_data_names_populates_list(self, h5_model, h5_file):
        h5_model._open_h5(h5_file)
        h5_model._refresh_h5_data_names()
        assert isinstance(h5_model._h5_data_names, list)
        assert len(h5_model._h5_data_names) > 0
        h5_model._close_h5()

    def test_data_names_are_strings(self, h5_model, h5_file):
        h5_model._open_h5(h5_file)
        h5_model._refresh_h5_data_names()
        for name in h5_model._h5_data_names:
            assert isinstance(name, str)
        h5_model._close_h5()

    def test_refresh_data_names_when_closed_does_nothing(self, h5_model):
        h5_model._h5saver_low = None
        h5_model._refresh_h5_data_names()   # must not raise
        assert h5_model._h5_data_names == []


# ---------------------------------------------------------------------------
# compute() end-to-end with a real H5 file
# ---------------------------------------------------------------------------

class TestComputeEndToEnd:

    def test_compute_emits_dte(self, h5_model, h5_file, mock_data_mixer):
        """compute() loads H5 data, evaluates each formula, emits result."""
        h5_model._open_h5(h5_file)
        h5_model._refresh_h5_data_names()

        # Pick the first discovered name and write a formula using it
        assert h5_model._h5_data_names, "H5 file must contain at least one data name"
        data_name = h5_model._h5_data_names[0]
        formula_text = f'result = {{{data_name}}} * 2'

        h5_model.settings.__getitem__ = MagicMock(return_value=formula_text)
        h5_model.compute()

        # The signal was emitted once
        mock_data_mixer.dte_computed_signal.emit.assert_called_once()
        dte_result: DataToExport = mock_data_mixer.dte_computed_signal.emit.call_args[0][0]
        assert len(dte_result.data) == 1
        assert dte_result.data[0].name == 'result'

    def test_compute_noop_when_no_file_open(self, h5_model, mock_data_mixer):
        h5_model._h5saver_low = None
        h5_model.compute()
        mock_data_mixer.dte_computed_signal.emit.assert_not_called()

    def test_compute_sequential_formulas(self, h5_model, h5_file, mock_data_mixer):
        """Second formula can reference the output of the first."""
        h5_model._open_h5(h5_file)
        h5_model._refresh_h5_data_names()

        data_name = h5_model._h5_data_names[0]
        formula_text = (
            f'a = {{{data_name}}} * 2\n'
            f'b = {{a}} + 1'
        )
        h5_model.settings.__getitem__ = MagicMock(return_value=formula_text)
        h5_model.compute()

        dte_result = mock_data_mixer.dte_computed_signal.emit.call_args[0][0]
        result_names = [dwa.name for dwa in dte_result.data]
        assert 'a' in result_names
        assert 'b' in result_names

    def test_compute_bad_formula_logs_and_continues(
            self, h5_model, h5_file, mock_data_mixer, caplog):
        """A broken formula logs an exception but does not abort remaining formulas."""
        import logging
        h5_model._open_h5(h5_file)
        h5_model._refresh_h5_data_names()

        data_name = h5_model._h5_data_names[0]
        formula_text = (
            'bad = {nonexistent_name_xyz}\n'
            f'good = {{{data_name}}} * 3'
        )
        h5_model.settings.__getitem__ = MagicMock(return_value=formula_text)

        with caplog.at_level(logging.ERROR):
            h5_model.compute()

        dte_result = mock_data_mixer.dte_computed_signal.emit.call_args[0][0]
        result_names = [dwa.name for dwa in dte_result.data]
        assert 'good' in result_names
        assert 'bad' not in result_names

    def test_process_dte_calls_compute(self, h5_model, h5_file, mock_data_mixer):
        """process_dte() satisfies the base-class contract by delegating to compute()."""
        h5_model._open_h5(h5_file)
        h5_model._refresh_h5_data_names()
        data_name = h5_model._h5_data_names[0]
        h5_model.settings.__getitem__ = MagicMock(
            return_value=f'r = {{{data_name}}}')

        dummy_dte = DataToExport('dummy', data=[])
        h5_model.process_dte(dummy_dte)

        mock_data_mixer.dte_computed_signal.emit.assert_called_once()
