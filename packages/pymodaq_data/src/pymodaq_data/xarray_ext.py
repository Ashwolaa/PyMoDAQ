# -*- coding: utf-8 -*-
"""xarray side of the DataWithAxes <-> xarray bridge

Importing this module (done by DataWithAxes.to_xarray / from_xarray) registers a ``.pmd`` accessor
on xarray Datasets and DataArrays::

    ds = dwa.to_xarray()
    ds.pmd.nav_dims                       # ('x', 'y'), read from the coordinates' pymodaq_role
    q = ds.pmd.quantify()                 # units computed by pint-xarray from here on
    result = (q['ch1'] / q['ch2']).mean('t')
    dwa_out = result.pmd.to_dwa(name='ratio', source='calculated')

Navigation vs signal is stored as a ``pymodaq_role`` attribute on each dimension's coordinate, as
coordinate attributes are carried by xarray through arithmetic, reductions and transposes
independently of the ``keep_attrs`` option.

Requires xarray; quantify also requires pint-xarray (``pip install 'pymodaq_data[xarray]'``).
"""
from __future__ import annotations

from typing import Iterable, List, Tuple, Type, Union

import numpy as np
import pint
import xarray as xr

from pymodaq_data import Unit
from pymodaq_data.data import Axis, DataSource, DataWithAxes, check_units


def short_units(units: str) -> str:
    """pymodaq's short units notation for a units string ('millimeter' -> 'mm'), '' if none"""
    units = str(units)
    if units in ('', 'dimensionless'):
        return ''
    try:
        return f'{Unit(units):~}'
    except (pint.errors.UndefinedUnitError, ValueError, AssertionError):
        return check_units(units)


def dequantify_if_needed(obj: Union[xr.Dataset, xr.DataArray]):
    """Turn pint-quantified variables back into plain arrays with a ``units`` attribute"""
    variables = obj.variables.values() if isinstance(obj, xr.Dataset) \
        else [obj.variable] + [coord.variable for coord in obj.coords.values()]
    if any(isinstance(var.data, pint.Quantity) for var in variables):
        import pint_xarray  # noqa: F401, registers the .pint accessor
        return obj.pint.dequantify()
    return obj


def _dim_coords(obj, dim: str) -> List[Tuple[str, xr.DataArray]]:
    """1D coordinates living on ``dim``, the index coordinate (named ``dim``) first"""
    coords = [(name, coord) for name, coord in obj.coords.items() if coord.dims == (dim,)]
    return sorted(coords, key=lambda item: item[0] != dim)


def dim_role(obj, dim: str) -> Union[str, None]:
    """'nav', 'sig' or None: the pymodaq_role stored on the coordinates of dimension ``dim``"""
    for _, coord in _dim_coords(obj, dim):
        if 'pymodaq_role' in coord.attrs:
            return coord.attrs['pymodaq_role']
    return None


def axes_for_dim(obj, dim: str, index: int, is_nav: bool, spread: bool) -> List[Axis]:
    """Axis objects describing dimension ``dim`` once placed at ``index`` in a DataWithAxes

    Numeric 1D coordinates become axes named after them, their CF ``long_name`` being the label:
    all of them for a spread navigation dimension (one per spread_order), otherwise only the
    primary one (the index coordinate first). Synthetic index coordinates written by to_xarray
    only become an axis for a navigation dimension, which DataWithAxes requires.
    """
    coords = [(name, coord) for name, coord in _dim_coords(obj, dim)
              if np.issubdtype(coord.dtype, np.number)]
    real = [(name, coord) for name, coord in coords if not coord.attrs.get('pymodaq_synthetic')]

    def make_axis(name: str, coord: xr.DataArray, spread_order: int) -> Axis:
        label = coord.attrs.get('long_name')
        if 'pymodaq_label' in coord.attrs:  # older formats: the label was the axis identifier
            name, label = coord.attrs['pymodaq_label'] or name, None
        return Axis(name, units=short_units(coord.attrs.get('units', '')),
                    data=np.asarray(coord.values), index=index, spread_order=spread_order,
                    label=None if label == name else label)

    if real and spread and is_nav:
        real.sort(key=lambda item: item[1].attrs.get('spread_order', np.inf))
        return [make_axis(name, coord, order) for order, (name, coord) in enumerate(real)]
    if real:
        return [make_axis(*real[0], 0)]
    if is_nav:
        return [Axis(dim, data=np.arange(obj.sizes[dim], dtype=float), index=index)]
    return []


class PymodaqAccessor:
    """pymodaq metadata helpers, available as ``.pmd`` on xarray Datasets and DataArrays"""

    def __init__(self, obj: Union[xr.Dataset, xr.DataArray]):
        self._obj = obj

    @property
    def nav_dims(self) -> Tuple[str, ...]:
        """Dimensions whose coordinates are tagged as navigation"""
        return tuple(dim for dim in self._obj.dims if dim_role(self._obj, dim) == 'nav')

    @property
    def sig_dims(self) -> Tuple[str, ...]:
        """Every dimension not tagged as navigation"""
        return tuple(dim for dim in self._obj.dims if dim not in self.nav_dims)

    def set_nav(self, *dims: str):
        """Return a copy with ``dims`` as navigation dimensions (moved first, in this order)
        and every other dimension as signal. A dimension without coordinate gets an index one."""
        obj = self._obj
        unknown = [dim for dim in dims if dim not in obj.dims]
        if unknown:
            raise ValueError(f'Dimensions {unknown} are not in {tuple(obj.dims)}')
        new_coords = {}
        for dim in obj.dims:
            role = 'nav' if dim in dims else 'sig'
            dim_coords = _dim_coords(obj, dim)
            if not dim_coords:
                new_coords[dim] = xr.Variable(dim, np.arange(obj.sizes[dim]),
                                              attrs={'pymodaq_role': role,
                                                     'pymodaq_synthetic': True})
            for name, coord in dim_coords:
                variable = coord.variable.copy()
                variable.attrs['pymodaq_role'] = role
                new_coords[name] = variable
        return obj.assign_coords(new_coords).transpose(*dims, ...)

    def quantify(self):
        """Attach the ``units`` attributes as pint units (pint-xarray), so that arithmetic
        computes the result units. from_xarray / to_dwa dequantify automatically."""
        import pint_xarray  # noqa: F401, registers the .pint accessor
        return self._obj.pint.quantify()

    def dequantify(self):
        """Inverse of quantify: back to plain arrays with ``units`` attributes"""
        return dequantify_if_needed(self._obj)

    def to_dwa(self, name: str = None, source: Union[DataSource, str] = None,
               nav: Iterable[str] = None, cls: Type[DataWithAxes] = DataWithAxes) -> DataWithAxes:
        """Convert to a DataWithAxes (or ``cls``), see DataWithAxes.from_xarray"""
        return cls.from_xarray(self._obj, name=name, source=source, nav=nav)


xr.register_dataset_accessor('pmd')(PymodaqAccessor)
xr.register_dataarray_accessor('pmd')(PymodaqAccessor)
