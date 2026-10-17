from typing import Optional, TYPE_CHECKING

from pymodaq.extensions.sequencer.utilities.switch_models.factory import SwitchModelFactory
from pymodaq.extensions.sequencer.utilities.holders.condition_holder_base import ConditionHolderBase

if TYPE_CHECKING:
    from pymodaq.extensions.sequencer.utilities.element_factory import SeqEltBase
    from pymodaq.extensions.sequencer.utilities.holders.branch_holder import BranchHolder

switch_factory = SwitchModelFactory()


class SwitchConditionHolder(ConditionHolderBase):
    """ Holds one pluggable SwitchModel - the SwitchModelBase/SwitchModelFactory
    specialization of ConditionHolderBase (see ConditionHolderBase and SwitchModelBase for why
    this is a separate model ecosystem rather than reusing ChoiceModelBase's).

    Unlike ConditionHolder, takes the owning element's BranchHolder as an explicit constructor
    argument and overrides `model`'s setter to keep it in sync: whenever the model changes (or
    the *current* model's own outcome set changes shape, via its `outcomes_changed` signal),
    calls `branches.rebuild()`. That dependency is a plain object reference passed in, not an
    assumption about what else happens to be attached to the owning element.
    """
    factory = switch_factory
    dict_key = 'switch_model'

    def __init__(self, elt: 'SeqEltBase', branches: 'BranchHolder',
                 combo_tooltip: Optional[str] = None):
        self.branches = branches
        super().__init__(elt, combo_tooltip)
        # Deliberately does NOT force the lazy model default to resolve here: doing so would
        # call _on_outcomes_changed() -> branches.rebuild(), whose first elt.mstate touch
        # stringifies elt via __repr__ - which (for SwitchElt) reads elt.condition, not yet
        # assigned while still inside this constructor. The owning element resolves it
        # explicitly instead, once self.condition has been assigned - see SwitchElt.__init__.

    @ConditionHolderBase.model.setter
    def model(self, value: str):
        if self._model is not None:
            self._model.outcomes_changed.disconnect(self._on_outcomes_changed)
        self._model = self.factory.get_model(value)(self.elt)
        self._model.outcomes_changed.connect(self._on_outcomes_changed)
        self._on_outcomes_changed()

    def _on_outcomes_changed(self):
        self.branches.rebuild(self.model.outcomes)
