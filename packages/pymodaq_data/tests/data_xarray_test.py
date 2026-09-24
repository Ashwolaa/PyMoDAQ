import numpy as np
import pytest

from pymodaq_data import data as data_mod

xr = pytest.importorskip('xarray')


class TestXarrayConversion:
    """Tests for DataWithAxes.to_xarray / from_xarray and DataToExport.to_xarray / from_xarray."""


    def test_to_xarray_dims_coords(self):
        axis = data_mod.Axis('time', units='s', data=np.linspace(0, 9, 10), index=0)
        dwa = data_mod.DataRaw('mydata', data=[np.arange(10, dtype=float)], axes=[axis])
        ds = dwa.to_xarray()
        assert 'time' in ds.dims
        assert 'time' in ds.coords
        assert np.allclose(ds.coords['time'].values, axis.get_data())
        assert ds.coords['time'].attrs['units'] == 's'

    def test_to_xarray_data_vars(self):
        arr1 = np.arange(5, dtype=float)
        arr2 = np.arange(5, 10, dtype=float)
        dwa = data_mod.DataRaw('mydata', data=[arr1, arr2], labels=['ch0', 'ch1'])
        ds = dwa.to_xarray()
        assert 'ch0' in ds.data_vars
        assert 'ch1' in ds.data_vars
        assert np.allclose(ds['ch0'].values, arr1)
        assert np.allclose(ds['ch1'].values, arr2)

    def test_to_xarray_attrs(self):
        nav_axis = data_mod.Axis('pos', units='mm', data=np.arange(3.), index=0)
        dwa = data_mod.DataRaw(
            'test', units='V', data=[np.zeros((3, 4))], labels=['ch0'],
            nav_indexes=(0,), axes=[nav_axis], origin='detector',
        )
        ds = dwa.to_xarray()
        assert ds.attrs['pymodaq_schema'] == data_mod.XARRAY_SCHEMA_VERSION
        assert ds.attrs['pymodaq_name'] == 'test'
        assert ds.attrs['pymodaq_origin'] == 'detector'
        assert ds.attrs['pymodaq_source'] == 'raw'
        assert ds.attrs['pymodaq_timestamp'] == dwa.timestamp
        assert ds['ch0'].attrs['units'] == 'V'
        assert ds.coords['pos'].attrs['pymodaq_role'] == 'nav'
        assert ds.coords['pos'].attrs['units'] == 'mm'
        # the signal dimension has no axis: it still gets an index coordinate carrying its role
        assert ds.coords['dim_1'].attrs['pymodaq_role'] == 'sig'
        assert ds.coords['dim_1'].attrs['pymodaq_synthetic']
        assert ds.pmd.nav_dims == ('pos',)

    def test_round_trip_1d(self):
        arr = np.linspace(1, 10, 20)
        axis = data_mod.Axis('x', units='nm', data=np.linspace(0, 19, 20), index=0)
        dwa = data_mod.DataRaw('signal', data=[arr], labels=['ch0'], axes=[axis])
        dwa2 = data_mod.DataWithAxes.from_xarray(dwa.to_xarray())
        assert dwa2.name == 'signal'
        assert np.allclose(dwa2[0], arr)
        axes = dwa2.get_axis_from_index(0)
        assert axes and axes[0].label == 'x'
        assert axes[0].units == 'nm'
        assert np.allclose(axes[0].get_data(), axis.get_data())

    def test_round_trip_2d_nav(self):
        arr = np.arange(12, dtype=float).reshape(3, 4)
        nav_axis = data_mod.Axis('nav', units='m', data=np.array([0., 1., 2.]), index=0)
        sig_axis = data_mod.Axis('sig', units='Hz', data=np.array([10., 20., 30., 40.]), index=1)
        dwa = data_mod.DataRaw(
            'nd', data=[arr], nav_indexes=(0,), axes=[nav_axis, sig_axis],
        )
        dwa2 = data_mod.DataWithAxes.from_xarray(dwa.to_xarray())
        assert tuple(dwa2.nav_indexes) == (0,)
        assert np.allclose(dwa2[0], arr)

    def test_round_trip_errors(self):
        arr = np.arange(5, dtype=float)
        err = arr * 0.1
        dwa = data_mod.DataRaw('errs', data=[arr], labels=['ch0'], errors=[err])
        ds = dwa.to_xarray()
        assert 'ch0_error' in ds.data_vars
        assert 'ch0' in ds.data_vars
        dwa2 = data_mod.DataWithAxes.from_xarray(ds)
        assert dwa2.errors is not None
        assert np.allclose(dwa2.errors[0], err)
        assert 'ch0_error' not in dwa2.labels

    def test_from_dataarray(self):
        da = xr.DataArray(
            np.arange(6, dtype=float),
            dims=['x'],
            coords={'x': np.arange(6, dtype=float)},
            name='myvar',
        )
        dwa = data_mod.DataWithAxes.from_xarray(da)
        assert dwa.name == 'from_xarray'
        assert np.allclose(dwa[0], da.values)

    def test_dte_to_datatree(self):
        dwa1 = data_mod.DataRaw('a', data=[np.zeros(5)])
        dwa2 = data_mod.DataRaw('b', data=[np.ones((3, 4))])
        dte = data_mod.DataToExport('myexp', data=[dwa1, dwa2])
        dt = dte.to_xarray()
        assert isinstance(dt, xr.DataTree)
        assert len(dt.children) == 2
        assert 'a' in dt.children
        assert 'b' in dt.children

    def test_dte_round_trip(self):
        dwa1 = data_mod.DataRaw('ch1', data=[np.arange(8, dtype=float)])
        dwa2 = data_mod.DataRaw('ch2', data=[np.arange(6, dtype=float).reshape(2, 3)])
        dte = data_mod.DataToExport('myexp', data=[dwa1, dwa2])
        dte2 = data_mod.DataToExport.from_xarray(dte.to_xarray())
        assert dte2.name == 'myexp'
        names = [dwa.name for dwa in dte2]
        assert 'ch1' in names
        assert 'ch2' in names
        ch1 = dte2.get_data_from_name('ch1')
        assert ch1.shape == (8,)
        ch2 = dte2.get_data_from_name('ch2')
        assert ch2.shape == (2, 3)


def make_dwa_3d(**kwargs):
    """ch1/ch2 on (x, y) navigation and t signal, in volts"""
    axes = [data_mod.Axis('x', units='mm', data=np.arange(2.), index=0),
            data_mod.Axis('y', units='mm', data=np.arange(3.), index=1),
            data_mod.Axis('t', units='s', data=np.arange(4.), index=2)]
    data = [np.random.rand(2, 3, 4), np.random.rand(2, 3, 4)]
    return data_mod.DataRaw('scan', data=data, labels=['ch1', 'ch2'], units='V', axes=axes,
                            nav_indexes=(0, 1), **kwargs)


class TestXarrayMetadataSurvival:
    """Navigation info rides on coordinates, so it survives xarray computations"""

    @pytest.mark.parametrize('keep_attrs', [False, True])
    def test_nav_survives_arithmetic_and_reduction(self, keep_attrs):
        ds = make_dwa_3d().to_xarray()
        with xr.set_options(keep_attrs=keep_attrs):
            result = (ds['ch1'] * 2 + ds['ch2']).mean('t')
        dwa = data_mod.DataWithAxes.from_xarray(result, name='res', source='calculated')
        assert dwa.nav_dim_names == ('x', 'y')
        assert dwa.nav_indexes == (0, 1)
        assert dwa.source == data_mod.DataSource.calculated
        assert dwa.name == 'res'

    def test_reduced_nav_dim_leaves_navigation(self):
        ds = make_dwa_3d().to_xarray()
        dwa = data_mod.DataWithAxes.from_xarray(ds.mean('x'))
        assert dwa.nav_dim_names == ('y',)
        assert dwa.sig_dim_names == ('t',)

    def test_transpose_restores_nav_first_layout(self):
        dwa = make_dwa_3d()
        dwa2 = data_mod.DataWithAxes.from_xarray(dwa.to_xarray().transpose('t', 'x', 'y'))
        assert dwa2.nav_indexes == (0, 1)
        assert dwa2.dim_names == ['x', 'y', 't']
        assert np.allclose(dwa2[0], dwa[0])

    def test_channels_with_different_dim_order(self):
        dwa = make_dwa_3d()
        ds = dwa.to_xarray()
        ds['ch2'] = ds['ch2'].transpose('t', 'y', 'x')
        dwa2 = data_mod.DataWithAxes.from_xarray(ds)
        assert np.allclose(dwa2[0], dwa[0])
        assert np.allclose(dwa2[1], dwa[1])

    def test_extracted_channel_keeps_its_own_label(self):
        ds = make_dwa_3d().to_xarray()
        dwa = data_mod.DataWithAxes.from_xarray(ds['ch2'])
        assert dwa.labels == ['ch2']
        assert dwa.units == 'V'
        assert dwa.nav_indexes == (0, 1)

    def test_errors_follow_transpose(self):
        dwa = make_dwa_3d(errors=[np.random.rand(2, 3, 4), np.random.rand(2, 3, 4)])
        ds = dwa.to_xarray()
        assert ds['ch1'].attrs['ancillary_variables'] == 'ch1_error'
        dwa2 = data_mod.DataWithAxes.from_xarray(ds.transpose('t', 'x', 'y'))
        assert np.allclose(dwa2.errors[1], dwa.errors[1])


class TestXarrayNaming:

    def test_repeated_axis_names_round_trip(self):
        """The duplicate is renamed (identifier) but keeps its label (display), both survive"""
        axes = [data_mod.Axis('x', data=np.arange(2.), index=0),
                data_mod.Axis('x', data=np.arange(3.), index=1),
                data_mod.Axis('x_1', data=np.arange(4.), index=2)]
        with pytest.warns(data_mod.AxisNameWarning):
            dwa = data_mod.DataRaw('d', data=[np.zeros((2, 3, 4))], labels=['ch'], axes=axes)
        ds = dwa.to_xarray()
        assert tuple(ds['ch'].dims) == ('x', 'x_2', 'x_1')
        assert ds.coords['x_2'].attrs['long_name'] == 'x'
        dwa2 = data_mod.DataWithAxes.from_xarray(ds)
        assert [axis.name for axis in dwa2.axes] == ['x', 'x_2', 'x_1']
        assert [axis.label for axis in dwa2.axes] == ['x', 'x', 'x_1']

    def test_axis_name_and_label_round_trip(self):
        axes = [data_mod.Axis('delay', units='ps', data=np.arange(3.), index=0,
                              label='Pump-probe delay'),
                data_mod.Axis('wl', units='nm', data=np.arange(4.), index=1)]
        dwa = data_mod.DataRaw('d', data=[np.zeros((3, 4))], labels=['Signal'], axes=axes,
                               nav_indexes=(0,))
        ds = dwa.to_xarray()
        assert ds.coords['delay'].attrs['long_name'] == 'Pump-probe delay'
        assert ds.coords['wl'].attrs['long_name'] == 'wl'
        assert ds['Signal'].attrs['long_name'] == 'Signal'
        dwa2 = data_mod.DataWithAxes.from_xarray(ds)
        assert [(axis.name, axis.label) for axis in dwa2.axes] == \
            [('delay', 'Pump-probe delay'), ('wl', 'wl')]
        assert dwa2.axes == dwa.axes

    def test_foreign_coordinate_long_name_becomes_label(self):
        da = xr.DataArray(np.zeros(3), dims=('x',),
                          coords={'x': ('x', np.arange(3.), {'long_name': 'Position',
                                                              'units': 'mm'})})
        axis = data_mod.DataWithAxes.from_xarray(da).axes[0]
        assert (axis.name, axis.label, axis.units) == ('x', 'Position', 'mm')

    def test_axisless_signal_dims_stay_axisless(self):
        dwa = data_mod.DataRaw('d', data=[np.zeros((2, 3))])
        dwa2 = data_mod.DataWithAxes.from_xarray(dwa.to_xarray())
        assert dwa2.axes == []

    def test_channel_label_colliding_with_axis_label(self):
        axis = data_mod.Axis('x', data=np.arange(3.), index=0)
        dwa = data_mod.DataRaw('d', data=[np.arange(3.)], labels=['x'], axes=[axis])
        dwa2 = data_mod.DataWithAxes.from_xarray(dwa.to_xarray())
        assert dwa2.labels == ['x']

    def test_spread_round_trip_independent_of_axes_order(self):
        npts = 5
        axes = [data_mod.Axis('b', data=np.random.rand(npts), index=0, spread_order=1),
                data_mod.Axis('a', data=np.random.rand(npts), index=0, spread_order=0),
                data_mod.Axis('t', data=np.arange(4.), index=1)]
        dwa = data_mod.DataRaw('s', distribution='spread', data=[np.random.rand(npts, 4)],
                               axes=axes, nav_indexes=(0,))
        ds = dwa.to_xarray()
        # the scattered points are the dimension, the spread axes non-index coordinates along it
        assert tuple(ds.sizes) == ('points', 't')
        assert ds.coords['a'].dims == ('points',) and ds.coords['b'].dims == ('points',)
        assert 'points' not in ds.indexes
        assert ds.pmd.nav_dims == ('points',)
        dwa2 = data_mod.DataWithAxes.from_xarray(ds)
        assert dwa2.distribution == data_mod.DataDistribution.spread
        assert dwa2.dim_names == ['points', 't']
        spread_b = dwa2.get_axis_from_index_spread(0, 1)
        assert spread_b.name == 'b'
        assert np.allclose(spread_b.get_data(), axes[0].get_data())

    def test_provenance_round_trip(self):
        dwa = make_dwa_3d()
        dwa.add_extra_attribute(exposure=0.5, comment='dark')
        dwa2 = data_mod.DataWithAxes.from_xarray(dwa.to_xarray())
        assert dwa2.timestamp == dwa.timestamp
        assert dwa2.exposure == 0.5
        assert dwa2.comment == 'dark'

    def test_legacy_pymodaq_label_is_the_axis_name(self):
        """Before axes had a name, coordinates stored the label, which was the identifier"""
        ds = xr.Dataset({'ch0': (('pos', 't'), np.zeros((2, 3)), {'pymodaq_label': 'ch0'})},
                        coords={'pos': ('pos', np.arange(2.), {'pymodaq_label': 'Position',
                                                                'pymodaq_role': 'nav'}),
                                't': ('t', np.arange(3.), {'pymodaq_label': 't',
                                                            'pymodaq_role': 'sig'})})
        dwa = data_mod.DataWithAxes.from_xarray(ds)
        assert [(axis.name, axis.label) for axis in dwa.axes] == [('Position', 'Position'),
                                                                   ('t', 't')]
        assert dwa.labels == ['ch0']

    def test_legacy_positional_nav_indexes(self):
        """Datasets written before pymodaq_schema stored nav as positional indexes (only
        meaningful in the stored dimension order)"""
        ds = xr.Dataset({'ch0': (('x', 't'), np.zeros((2, 3)))},
                        coords={'x': ('x', np.arange(2.)), 't': ('t', np.arange(3.))},
                        attrs={'pymodaq_nav_indexes': [0], 'pymodaq_units': 'mm',
                               'pymodaq_labels': ['chan']})
        dwa = data_mod.DataWithAxes.from_xarray(ds)
        assert dwa.nav_dim_names == ('x',)
        assert dwa.units == 'mm'
        assert dwa.labels == ['chan']


class TestPmdAccessor:

    def test_set_nav(self):
        dwa = make_dwa_3d()
        ds = dwa.to_xarray().pmd.set_nav('t')
        assert ds.pmd.nav_dims == ('t',)
        dwa2 = ds.pmd.to_dwa()
        assert dwa2.nav_dim_names == ('t',)
        assert dwa2.sig_dim_names == ('x', 'y')

    def test_set_nav_on_foreign_dataarray(self):
        da = xr.DataArray(np.zeros((2, 3)), dims=('a', 'b'))
        dwa = da.pmd.set_nav('b').pmd.to_dwa()
        assert dwa.nav_indexes == (0,)
        assert dwa.shape == (3, 2)

    def test_explicit_nav_overrides_roles(self):
        ds = make_dwa_3d().to_xarray()
        dwa = data_mod.DataWithAxes.from_xarray(ds, nav=['t'])
        assert dwa.nav_dim_names == ('t',)
        with pytest.raises(ValueError):
            data_mod.DataWithAxes.from_xarray(ds, nav=['nope'])

    def test_quantify_computes_units(self):
        pytest.importorskip('pint_xarray')
        dwa_v = data_mod.DataRaw('v', data=[np.full(3, 2.)], units='V', labels=['v'])
        dwa_i = data_mod.DataRaw('i', data=[np.full(3, 4.)], units='mA', labels=['i'])
        ratio = dwa_v.to_xarray().pmd.quantify()['v'] / dwa_i.to_xarray().pmd.quantify()['i']
        dwa = ratio.pmd.to_dwa(name='R', source='calculated')
        assert data_mod.Unit(dwa.units) == data_mod.Unit('V/mA')
        assert np.allclose(dwa.units_as('ohm', inplace=False)[0], 500.)
