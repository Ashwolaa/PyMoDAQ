from typing import Any

from qtpy import QtCore

from pymodaq_data import DataToExport, DataDim
from pymodaq_gui.parameter.pymodaq_ptypes import GroupParameter, registerParameterType
from pymodaq.extensions.sequencer.utilities.switch_models.factory import SwitchModelFactory
from pymodaq.extensions.sequencer.utilities.switch_models.model import SwitchModelBase
from pymodaq.extensions.sequencer.utilities.element_factory import ElementError


switch_factory = SwitchModelFactory()


class BoundariesGroupParameter(GroupParameter):
    """ Addable/removable list of boundary values for BandsSwitchModel.

    Displays an "Add boundary" menu entry; when clicked, emits `sigBoundaryAdded` so the owning
    BandsSwitchModel (which alone knows how to assign a new boundary its stable row id) does
    the actual work. Removal reuses the base Parameter's own `removable`/`sigChildRemoved`
    (same pattern CompositeChoiceModel uses for its condition rows), no custom signal needed.
    """
    sigBoundaryAdded = QtCore.Signal()

    def __init__(self, **opts):
        opts['type'] = 'bands_boundaries'
        opts.setdefault('addText', 'Add boundary')
        super().__init__(**opts)

    def addNew(self, typ=None):
        self.sigBoundaryAdded.emit()


registerParameterType('bands_boundaries', BoundariesGroupParameter, override=True)


@SwitchModelFactory.register_switch()
class BandsSwitchModel(SwitchModelBase):
    """ Classifies a probed value into one of N bands defined by N-1 boundary values -
    mirrors ThresholdChoiceModel's detector-probing logic (detectors/probe_data/data_name),
    generalized from a single threshold to any number of ordered boundaries.

    Bands are keyed by stable ids: each band's id is the stable row id of the boundary that
    bounds it from above; the top band (above every boundary, including when there are none)
    uses the fixed sentinel id TOP_BAND_ID. Removing a boundary removes exactly the band it
    bounded and widens the next band down to absorb the gap - that next band's own id (and so
    its configured target) is unaffected.
    """
    model_name = 'bands'
    TOP_BAND_ID = -1

    params = [
        {'title': 'Detectors', 'name': 'detectors', 'type': 'itemselect'},
        {'title': 'Probe Data', 'name': 'probe_data', 'type': 'action'},
        {'title': 'Data0D', 'name': 'data_name', 'type': 'list'},
        {'title': 'Boundaries', 'name': 'boundaries', 'type': 'bands_boundaries'},
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings.child('probe_data').sigActivated.connect(self.probe_data)
        self.settings['detectors'] = dict(all_items=self.modules_manager.detectors_name,
                                          selected=self.modules_manager.detectors_name)
        self._next_boundary_ind = 0

        boundaries_param: BoundariesGroupParameter = self.settings.child('boundaries')
        boundaries_param.sigBoundaryAdded.connect(self.add_boundary)
        boundaries_param.sigChildRemoved.connect(self._on_boundary_removed)

        self._recompute_outcomes()

    def updated_module_manager(self):
        """ called whenever the parent modules manager is updated """
        available = self.modules_manager.detectors_name
        selected = [name for name in self.settings['detectors']['selected'] if name in available]
        self.settings['detectors'] = dict(all_items=available, selected=selected)

    def probe_data(self):
        self.modules_manager.selected_detectors_name = self.settings['detectors']['selected']
        dte = self.modules_manager.get_det_data_list()
        data0D_names = dte.get_full_names(DataDim.Data0D)
        self.settings.child('data_name').setLimits(data0D_names)
        if len(data0D_names) > 0:
            self.settings['data_name'] = data0D_names[0]

    def add_boundary(self, value: float = 0.0, row_id: int = None):
        """ Add a boundary row. `row_id` is normally auto-assigned (the next unused stable id);
        from_dict passes the originally-saved id explicitly, so a reloaded sequence's _go_to
        target assignments (keyed by these same ids) still line up correctly.
        """
        if row_id is None:
            row_id = self._next_boundary_ind
        self._next_boundary_ind = max(self._next_boundary_ind, row_id + 1)
        row_name = f'boundary_{row_id}'
        self.settings.child('boundaries').addChild(
            {'title': f'Boundary {row_id}', 'name': row_name, 'type': 'float', 'value': value,
             'removable': True})
        self._recompute_outcomes()

    def _on_boundary_removed(self, parent, removed_row):
        self._recompute_outcomes()

    def _sorted_boundaries(self) -> list[tuple[int, float]]:
        """ (stable row id, value) for every boundary, ascending by value """
        rows = self.settings.child('boundaries').children()
        parsed = [(int(row.name().split('_')[1]), row.value()) for row in rows]
        return sorted(parsed, key=lambda pair: pair[1])

    def _recompute_outcomes(self):
        boundaries = self._sorted_boundaries()
        outcomes = {}
        for i, (row_id, value) in enumerate(boundaries):
            label = f'< {value:g}' if i == 0 else f'[{boundaries[i - 1][1]:g}, {value:g})'
            outcomes[row_id] = label
        outcomes[self.TOP_BAND_ID] = (f'>= {boundaries[-1][1]:g}' if boundaries else 'any value')
        if outcomes != self._outcomes:
            self._outcomes = outcomes
            self.outcomes_changed.emit()

    def _band_for(self, value: float) -> int:
        for row_id, boundary in self._sorted_boundaries():
            if value < boundary:
                return row_id
        return self.TOP_BAND_ID

    def evaluate(self, dte: DataToExport) -> int:
        if len(self.settings['detectors']['selected']) > 0:
            self.modules_manager.selected_detectors_name = self.settings['detectors']['selected']
            self.modules_manager.connect_detectors()
            dte = self.modules_manager.grab_data()
            self.modules_manager.connect_detectors(False)
        else:
            dte = DataToExport('Grab')

        return self._band_for(self.process_dte(dte))

    def process_dte(self, dte: DataToExport) -> float:
        dwa = dte.get_data_from_full_name(self.settings['data_name'])
        return dwa.value()

    def check_set_is_valid(self):
        """ Check if the current settings of this model are valid """
        if not self.parent_elt.dashboard.experiment_manager.entry_applied:
            raise ElementError('No Experiment has been applied in the DashBoard')
        if len(self.settings['detectors']['selected']) == 0:
            raise ElementError(f'Element {self.parent_elt} has no detector selected')
        for det_name in self.settings['detectors']['selected']:
            if det_name not in self.parent_elt.dashboard.modules_manager.detectors_name:
                raise ElementError(f'Element {self.parent_elt}: the selected detector '
                                   f'{det_name} is not existing in the DashBoard')
        if self.settings['data_name'] is None or self.settings['data_name'] == '':
            raise ElementError(f'Element {self.parent_elt} has no data name set')

    def to_dict(self) -> dict[str, Any]:
        """ adds attribute to a dict in order to produce a human readable
        representation/configuration for this model params
        """
        return {'detectors': self.settings['detectors'],
                'data_names': self.settings.child('data_name').opts['limits'],
                'data_name': self.settings['data_name'],
                'boundaries': [{'id': row_id, 'value': value}
                               for row_id, value in self._sorted_boundaries()],
                }

    def from_dict(self, dict_config: dict[str, Any]):
        """ Create/set the custom part of the element to finish initialization
        using setters, attribute assignment or methods
        """
        self.settings['detectors'] = dict_config.pop('detectors')
        self.settings.child('data_name').setLimits(dict_config.pop('data_names'))
        self.settings['data_name'] = dict_config.pop('data_name')
        for entry in dict_config.pop('boundaries'):
            self.add_boundary(entry['value'], row_id=entry['id'])
