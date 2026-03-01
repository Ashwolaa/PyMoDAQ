"""Tests for _collect_h5_datasets (pure Python, no Qt required).

Covers:
  * empty file returns empty dict
  * single scan + detector + channel returns correct key and xr.Dataset
  * two scans return two distinct keys (no collision)
  * key is relative to /RawData and contains full path
"""
from __future__ import annotations

import numpy as np
import pytest

from pymodaq_data.h5modules import saving
from pymodaq_data.h5modules.data_saving import DataSaverLoader
from pymodaq_data import data as data_mod


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_dwa(name='sig', n=10) -> data_mod.DataWithAxes:
    arr = np.linspace(0.0, 1.0, n)
    dwa = data_mod.DataWithAxes(
        name,
        source=data_mod.DataSource['raw'],
        data=[arr],
    )
    dwa.create_missing_axes()
    return dwa


def _build_h5(tmp_path, scans: list[list[str]]) -> 'Path':
    """Build a minimal PyMoDAQ-style H5 file.

    Parameters
    ----------
    scans:
        list of scan specs; each spec is a list of channel names to add to
        that scan's Detector000 group.
        Example: [['CH0', 'CH1'], ['CH0']] creates Scan000 (CH0, CH1)
        and Scan001 (CH0).
    """
    from pathlib import Path

    path = tmp_path / 'test.h5'
    h5saver = saving.H5SaverLowLevel(backend='h5py')
    h5saver.init_file(path, new_file=True)

    for channels in scans:
        scan_group = h5saver.add_scan_group()          # Scan000, Scan001, …
        det_group = h5saver.add_det_group(scan_group)  # Detector000

        for ch_name in channels:
            ch_group = h5saver.get_set_group(det_group, ch_name, ch_name)
            DataSaverLoader(h5saver).add_data(ch_group, _make_dwa(ch_name))

    h5saver.close_file()
    return path


# ── tests ─────────────────────────────────────────────────────────────────────


class TestCollectH5Datasets:

    def _load(self, tmp_path, scans):
        """Build an H5, open for reading, collect datasets, close."""
        from pymodaq.extensions.data_mixer.gui.formatters import _collect_h5_datasets

        path = _build_h5(tmp_path, scans)
        h5saver, _ = saving.H5SaverLowLevel.open_for_reading(path)
        try:
            result = _collect_h5_datasets(h5saver)
        finally:
            h5saver.close_file()
        return result

    def test_empty_file_returns_empty_dict(self, tmp_path):
        """A file with no data nodes should return {}."""
        from pymodaq.extensions.data_mixer.gui.formatters import _collect_h5_datasets

        path = tmp_path / 'empty.h5'
        h5saver = saving.H5SaverLowLevel(backend='h5py')
        h5saver.init_file(path, new_file=True)
        h5saver.close_file()

        h5saver2, _ = saving.H5SaverLowLevel.open_for_reading(path)
        try:
            result = _collect_h5_datasets(h5saver2)
        finally:
            h5saver2.close_file()

        assert result == {}

    def test_single_scan_single_channel_found(self, tmp_path):
        """One scan + one channel → one entry in result."""
        result = self._load(tmp_path, [['CH0']])
        assert len(result) == 1

    def test_single_scan_key_contains_scan_and_channel(self, tmp_path):
        """Key should encode the full H5 path (scan / detector / channel)."""
        result = self._load(tmp_path, [['CH0']])
        key = next(iter(result))
        # Key should contain the scan group name and channel name
        assert 'Scan' in key or 'scan' in key.lower()
        assert 'CH0' in key

    def test_single_scan_value_is_xr_dataset(self, tmp_path):
        """Values must be xr.Dataset instances."""
        import xarray as xr
        result = self._load(tmp_path, [['CH0']])
        for val in result.values():
            assert isinstance(val, xr.Dataset)

    def test_two_scans_same_channel_no_collision(self, tmp_path):
        """Two scans each with CH0 → two distinct entries."""
        result = self._load(tmp_path, [['CH0'], ['CH0']])
        assert len(result) == 2, (
            f"Expected 2 entries, got {len(result)}: {list(result)}"
        )

    def test_two_scans_distinct_keys(self, tmp_path):
        """Two scans produce different keys (Scan000 vs Scan001)."""
        result = self._load(tmp_path, [['CH0'], ['CH0']])
        keys = list(result.keys())
        assert keys[0] != keys[1]

    def test_multiple_channels_in_one_scan(self, tmp_path):
        """Multiple channels in one scan → multiple entries."""
        result = self._load(tmp_path, [['CH0', 'CH1', 'CH2']])
        assert len(result) == 3

    def test_mixed_scans_correct_total(self, tmp_path):
        """2 scans, first has 2 channels, second has 1 → 3 entries total."""
        result = self._load(tmp_path, [['CH0', 'CH1'], ['CH0']])
        assert len(result) == 3
