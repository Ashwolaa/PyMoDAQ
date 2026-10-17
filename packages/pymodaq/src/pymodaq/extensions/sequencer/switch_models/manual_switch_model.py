from typing import Any

from qtpy import QtCore

from pymodaq_data import DataToExport
from pymodaq_gui.parameter.pymodaq_ptypes import GroupParameter, registerParameterType
from pymodaq.extensions.sequencer.utilities.switch_models.factory import SwitchModelFactory
from pymodaq.extensions.sequencer.utilities.switch_models.model import SwitchModelBase
from pymodaq.extensions.sequencer.utilities.element_factory import ElementError


switch_factory = SwitchModelFactory()


class OutcomesGroupParameter(GroupParameter):
    """ Addable/removable list of named outcomes for ManualSwitchModel.

    Displays an "Add outcome" menu entry; when clicked, emits `sigOutcomeAdded` so the owning
    ManualSwitchModel (which alone knows how to assign a new outcome its stable row id) does the
    actual work. Removal reuses the base Parameter's own `removable`/`sigChildRemoved` (same
    pattern BandsSwitchModel's boundaries and CompositeChoiceModel's conditions use), no custom
    signal needed.
    """
    sigOutcomeAdded = QtCore.Signal()

    def __init__(self, **opts):
        opts['type'] = 'manual_outcomes'
        opts.setdefault('addText', 'Add outcome')
        super().__init__(**opts)

    def addNew(self, typ=None):
        self.sigOutcomeAdded.emit()


registerParameterType('manual_outcomes', OutcomesGroupParameter, override=True)


@SwitchModelFactory.register_switch()
class ManualSwitchModel(SwitchModelBase):
    """ Picks one of N user-named outcomes by hand - no detector/dashboard coupling at all.

    `evaluate()` just returns whichever outcome is currently selected in 'selected'; the switch
    is set by hand (at design time, or live while a sequence is open), not derived from any
    measurement. This is SwitchElt's trivial default - the N-way analogue of ChoiceElt's
    parameter-less `true`/`false` - so a brand new SwitchElt doesn't force a user into
    detector-probing params (that's BandsSwitchModel's job, for when the branch really is
    data-driven) before they've decided what kind of switch they want. Also useful standalone,
    to force one branch while building/testing the rest of a sequence.
    """
    model_name = 'manual'

    params = [
        {'title': 'Outcomes', 'name': 'outcomes', 'type': 'manual_outcomes'},
        {'title': 'Selected', 'name': 'selected', 'type': 'list', 'limits': []},
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._next_outcome_ind = 0
        outcomes_param: OutcomesGroupParameter = self.settings.child('outcomes')
        outcomes_param.sigOutcomeAdded.connect(self.add_outcome)
        outcomes_param.sigChildRemoved.connect(self._on_outcome_removed)
        self.add_outcome('Outcome 1')
        self.add_outcome('Outcome 2')

    def add_outcome(self, label: str = None, row_id: int = None):
        """ Add an outcome row. `row_id` is normally auto-assigned (the next unused stable id);
        from_dict passes the originally-saved id explicitly, so a reloaded sequence's _go_to
        target assignments (keyed by these same ids) still line up correctly.
        """
        if row_id is None:
            row_id = self._next_outcome_ind
        self._next_outcome_ind = max(self._next_outcome_ind, row_id + 1)
        if label is None:
            label = f'Outcome {row_id}'
        row_name = f'outcome_{row_id}'
        self.settings.child('outcomes').addChild(
            {'title': row_name, 'name': row_name, 'type': 'str', 'value': label,
             'removable': True})
        self._recompute_outcomes()

    def _on_outcome_removed(self, parent, removed_row):
        self._recompute_outcomes()

    def _recompute_outcomes(self):
        outcomes = {int(row.name().split('_')[1]): row.value()
                    for row in self.settings.child('outcomes').children()}
        if outcomes == self._outcomes:
            return
        self._outcomes = outcomes
        selected_param = self.settings.child('selected')
        previous = selected_param.value()
        # dict limits: display label -> stored value (the stable row id), so 'selected' holds
        # the id directly rather than needing to look a label back up (and risk ambiguity if two
        # outcomes ever share a label).
        selected_param.setLimits({label: row_id for row_id, label in outcomes.items()})
        if previous not in outcomes and len(outcomes) > 0:
            selected_param.setValue(next(iter(outcomes)))
        self.outcomes_changed.emit()

    def evaluate(self, dte: DataToExport) -> int:
        return self.settings['selected']

    def check_set_is_valid(self):
        if len(self._outcomes) == 0:
            raise ElementError(f'Element {self.parent_elt} has no outcome defined')

    def to_dict(self) -> dict[str, Any]:
        return {'outcomes': dict(self._outcomes), 'selected': self.settings['selected']}

    def from_dict(self, dict_config: dict[str, Any]):
        for row in list(self.settings.child('outcomes').children()):
            row.remove()
        self._outcomes = {}
        for row_id, label in dict_config.pop('outcomes').items():
            self.add_outcome(label, row_id=int(row_id))
        self.settings['selected'] = dict_config.pop('selected')
