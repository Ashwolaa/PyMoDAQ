from typing import Any

from serializall import SerializableFactory

from pymodaq_data import DataToExport

from pymodaq.extensions.sequencer.utilities.element_factory import SeqEltBase, SeqEltFactory
from pymodaq.extensions.sequencer.utilities.holders.branch_holder import BranchHolder
from pymodaq.extensions.sequencer.utilities.holders.switch_condition_holder import SwitchConditionHolder
from pymodaq.extensions.sequencer.utilities.widget_with_toolbar import WidgetWithToolbar


ser_factory = SerializableFactory()


@SerializableFactory.register_decorator()
@SeqEltFactory.register_elt()
class SwitchElt(SeqEltBase):
    """ Branches to one of N other elements (by id, anywhere in the tree) based on a pluggable
    N-way condition - the general case ChoiceElt's True/False is a fixed-at-2 special case of.

    Composes `branches` (BranchHolder, same one ChoiceElt uses) and `condition`
    (SwitchConditionHolder). Unlike ChoiceElt, branches' labels aren't fixed - they come from
    whichever model is plugged in - so construction order matters in one more way: `branches`
    is built empty first (so nothing touches elt.mstate yet) and assigned, then `condition` is
    built and assigned, and only *then* is its model's lazy default forced to resolve - by
    which point both self.branches and self.condition already exist, so whatever gets
    triggered along the way (elt.mstate's first touch -> __repr__ -> self.condition/
    self.branches) finds them. All three of these are separate, visible lines below, not a
    cooperative-super()-unwind-order puzzle (see ChoiceElt/git history for what that looked
    like before this was composition).
    """

    elt_name = 'switch'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.branches = BranchHolder(self, {})
        self.condition = SwitchConditionHolder(self, self.branches)
        _ = self.condition.model  # now safe: both self.branches and self.condition exist

    def do_things_with_dashboard(self):
        self.condition.bind_to_dashboard()

    @property
    def switch_model(self):
        return self.condition.model

    @switch_model.setter
    def switch_model(self, value: str):
        self.condition.model = value

    def _create_widget(self, base_widget: WidgetWithToolbar) -> WidgetWithToolbar:
        base_widget = self.condition.create_widget(base_widget)
        self.branches.create_widgets(base_widget)
        return base_widget

    def to_dict_custom(self) -> dict[str, Any]:
        dict_config = {'go_to': dict(self.branches._go_to)}
        dict_config.update(self.condition.to_dict())
        return dict_config

    def from_dict_custom(self, dict_config: dict[str, Any]):
        go_to = dict_config.pop('go_to')
        # Sets switch_model, which (re)builds the model's outcomes (boundaries, for
        # BandsSwitchModel) and - via SwitchConditionHolder - branches' _go_to/
        # value_transitions with the restored stable ids, all targets still None.
        self.condition.from_dict(dict_config)
        for branch, target_id in go_to.items():
            branch = int(branch)  # a YAML/JSON round-trip may have stringified dict keys
            if target_id is not None and branch in self.branches._go_to:
                self.branches.set_go_to(branch, target_id)

    def _eq(self, other: 'SwitchElt') -> bool:
        if not hasattr(other, 'branches'):
            return False
        if self.branches._go_to != other.branches._go_to:
            return False
        return self.condition.eq(other.condition)

    def __repr__(self):
        condition = getattr(self, 'condition', None)
        branches = getattr(self, 'branches', None)
        if condition is None or branches is None:
            return super().__repr__()
        return f'{super().__repr__()} - Switch: {condition.model.model_name} - {branches._go_to}'

    def _execute(self, dte: DataToExport = None):
        self.switch_model.execute(dte)

    def check_set_is_valid(self) -> bool:
        self.branches.check_set_is_valid()
        self.condition.check_set_is_valid()
