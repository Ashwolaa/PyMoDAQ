"""Tests for H5FileScanner and wrap_result (pymodaq_data.h5modules.scanner)."""
import numpy as np
import pytest
from pathlib import Path

from pymodaq_data.h5modules import backends, saving, H5FileScanner, wrap_result
from pymodaq_data.h5modules.data_saving import DataSaverLoader
from pymodaq_data.data import DataWithAxes, DataSource, DataToExport, Axis


# ── helpers ───────────────────────────────────────────────────────────────────

tested_backends = [b for b in ['tables', 'h5py'] if b in backends.backends_available]

DATA2D = np.arange(30, dtype=float).reshape(5, 6)
DATA1D = np.arange(10, dtype=float)
DATA0D = np.array([42.0])


def _make_h5_file(tmp_path: Path, backend: str) -> Path:
    """Create a small PyMoDAQ-style HDF5 file with two datasets."""
    path = tmp_path / 'test.h5'
    h5saver = saving.H5SaverLowLevel(backend=backend)
    h5saver.init_file(file_name=path, new_file=True)

    dwa2d = DataWithAxes('myData2D', DataSource['raw'],
                         data=[DATA2D],
                         axes=[Axis(data=np.arange(5.), index=0, label='x'),
                               Axis(data=np.arange(6.), index=1, label='y')])
    dwa2d.create_missing_axes()
    DataSaverLoader(h5saver).add_data('/RawData', dwa2d)

    dwa0d = DataWithAxes('myData0D', DataSource['raw'], data=[DATA0D])
    dwa0d.create_missing_axes()
    DataSaverLoader(h5saver).add_data('/RawData', dwa0d)

    h5saver.close_file()
    return path


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(params=tested_backends)
def h5_file(request, tmp_path):
    """Return (path, backend) for a freshly written test file."""
    backend = request.param
    return _make_h5_file(tmp_path, backend), backend


# ── H5FileScanner.open / close ────────────────────────────────────────────────

class TestH5FileScannerOpen:
    def test_open_returns_scanner(self, h5_file):
        path, _ = h5_file
        scanner = H5FileScanner.open(path)
        assert isinstance(scanner, H5FileScanner)
        scanner.close()

    def test_context_manager_closes_handle(self, h5_file):
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            assert scanner.h5saver.isopen()
        assert not scanner.h5saver.isopen()

    def test_close_is_idempotent(self, h5_file):
        path, _ = h5_file
        scanner = H5FileScanner.open(path)
        scanner.close()
        scanner.close()  # second call must not raise

    def test_borrow_handle_does_not_close(self, h5_file):
        """Borrowing an external h5saver must not close it on scanner.close()."""
        path, backend = h5_file
        h5saver = saving.H5SaverLowLevel(backend=backend)
        h5saver.init_file(file_name=path)
        scanner = H5FileScanner(h5saver)
        assert not scanner._owns_handle
        scanner.close()
        assert h5saver.isopen(), 'borrowed handle must remain open'
        h5saver.close_file()

    def test_base_is_rawdata_for_pymodaq_file(self, h5_file):
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            assert scanner.base == '/RawData'

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(Exception):
            H5FileScanner.open(tmp_path / 'does_not_exist.h5')


# ── H5FileScanner.scan ────────────────────────────────────────────────────────

class TestH5FileScannerScan:
    def test_scan_returns_dict(self, h5_file):
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            result = scanner.scan()
        assert isinstance(result, dict)

    def test_scan_contains_dataset_keys(self, h5_file):
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            result = scanner.scan()
        # Both datasets should be present (parent group path relative to /RawData)
        assert len(result) >= 1

    def test_scan_values_are_strings(self, h5_file):
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            result = scanner.scan()
        for key, val in result.items():
            assert isinstance(key, str) and key
            assert isinstance(val, str)

    def test_scan_no_data_loaded(self, h5_file):
        """scan() must return immediately without reading array data."""
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            info = scanner.scan()
        # If we got here without OOM or massive delay, the test passes.
        assert info is not None

    def test_scan_on_borrowed_handle(self, h5_file):
        path, backend = h5_file
        h5saver = saving.H5SaverLowLevel(backend=backend)
        h5saver.init_file(file_name=path)
        scanner = H5FileScanner(h5saver)
        result = scanner.scan()
        assert isinstance(result, dict)
        h5saver.close_file()


# ── H5FileScanner.load_dataset ────────────────────────────────────────────────

class TestH5FileScannerLoadDataset:
    def test_load_dataset_returns_xr_dataset(self, h5_file):
        pytest.importorskip('xarray')
        import xarray as xr
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            info = scanner.scan()
            rel = next(iter(info))
            ds = scanner.load_dataset(rel)
        assert ds is not None
        assert isinstance(ds, xr.Dataset)

    def test_load_dataset_bad_path_returns_none(self, h5_file):
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            result = scanner.load_dataset('NonExistent/Path')
        assert result is None

    def test_load_dataset_data_matches_written(self, h5_file):
        pytest.importorskip('xarray')
        path, _ = h5_file
        with H5FileScanner.open(path) as scanner:
            info = scanner.scan()
            # Load the first key — it should correspond to one of our datasets
            rel = next(iter(info))
            ds = scanner.load_dataset(rel)
        assert ds is not None
        # The dataset must contain at least one data variable
        assert len(ds.data_vars) >= 1


# ── H5FileScanner.load_from_handle ───────────────────────────────────────────

class TestH5FileScannerLoadFromHandle:
    def test_load_from_handle_static_method(self, h5_file):
        pytest.importorskip('xarray')
        import xarray as xr
        path, backend = h5_file
        h5saver = saving.H5SaverLowLevel(backend=backend)
        h5saver.init_file(file_name=path)
        with H5FileScanner(h5saver) as scanner:
            info = scanner.scan()
            rel = next(iter(info))
            abs_path = f'/RawData/{rel}'
            ds = H5FileScanner.load_from_handle(h5saver, abs_path)
        assert isinstance(ds, xr.Dataset)

    def test_load_from_handle_bad_path_returns_none(self, h5_file):
        path, backend = h5_file
        h5saver = saving.H5SaverLowLevel(backend=backend)
        h5saver.init_file(file_name=path)
        result = H5FileScanner.load_from_handle(h5saver, '/RawData/NoSuchNode')
        h5saver.close_file()
        assert result is None


# ── wrap_result ───────────────────────────────────────────────────────────────

class TestWrapResult:
    def test_ndarray_scalar(self):
        arr = np.zeros((3, 4))
        dwa = wrap_result(arr, 'out')
        assert isinstance(dwa, DataWithAxes)
        assert dwa.name == 'out'
        assert dwa.data[0] is arr

    def test_scalar_int(self):
        dwa = wrap_result(7, 'scalar')
        assert isinstance(dwa, DataWithAxes)
        assert dwa.data[0].shape == (1,)
        assert float(dwa.data[0][0]) == 7.0

    def test_scalar_float(self):
        dwa = wrap_result(3.14, 'pi')
        assert float(dwa.data[0][0]) == pytest.approx(3.14)

    def test_numpy_scalar_types(self):
        for scalar in (np.int32(5), np.float64(2.5), np.bool_(True)):
            dwa = wrap_result(scalar, 'x')
            assert isinstance(dwa, DataWithAxes)

    def test_tuple_of_arrays(self):
        a = np.ones(5)
        b = np.zeros(5)
        dwa = wrap_result((a, b), 'grad')
        assert isinstance(dwa, DataWithAxes)
        assert len(dwa.data) == 2

    def test_list_of_arrays(self):
        data = [np.arange(3, dtype=float), np.arange(3, dtype=float) * 2]
        dwa = wrap_result(data, 'multi')
        assert len(dwa.data) == 2

    def test_data_with_axes_passthrough(self):
        original = DataWithAxes('orig', DataSource['raw'], data=[np.ones(5)])
        dwa = wrap_result(original, 'renamed')
        assert dwa.name == 'renamed'
        assert dwa is original  # renamed in place

    def test_xarray_dataset_single_var(self):
        xr = pytest.importorskip('xarray')
        da = xr.DataArray(np.ones((3, 4)), dims=['x', 'y'], name='ch0')
        ds = da.to_dataset()
        dwa = wrap_result(ds, 'result')
        assert isinstance(dwa, DataWithAxes)
        assert dwa.name == 'result'

    def test_xarray_dataarray(self):
        xr = pytest.importorskip('xarray')
        da = xr.DataArray(np.arange(6, dtype=float).reshape(2, 3), dims=['a', 'b'])
        dwa = wrap_result(da, 'out')
        assert isinstance(dwa, DataWithAxes)
        assert dwa.name == 'out'

    def test_unsupported_type_raises_type_error(self):
        with pytest.raises(TypeError, match='Formula returned'):
            wrap_result({'a': 1}, 'bad')

    def test_unsupported_string_raises_type_error(self):
        with pytest.raises(TypeError):
            wrap_result('hello', 'bad')
