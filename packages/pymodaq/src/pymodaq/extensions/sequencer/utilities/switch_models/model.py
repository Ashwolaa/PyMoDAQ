import importlib
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qtpy import QtCore
from serializall import SerializableFactory

from pymodaq.utils.managers.modules import ModulesManager
from pymodaq_data import DataToExport
from pymodaq_gui.managers.parameter_manager import ParameterManager
from pymodaq_utils.abstract import abstract_attribute
from pymodaq_utils.utils import get_entrypoints
from pymodaq_utils.logger import set_logger, get_module_name


if TYPE_CHECKING:
    from pymodaq.extensions.sequencer.utilities.elements.switch import SwitchElt

logger = set_logger(get_module_name(__file__))
ser_factory = SerializableFactory()


class SwitchModelBase(QtCore.QObject, ParameterManager):
    """ Pluggable condition for SwitchElt: evaluates to one of several declared outcomes
    instead of ChoiceModelBase's strict bool (see ChoiceModelBase for why the two contracts
    aren't shared/merged).

    Outcomes are keyed by stable integer ids, not positions (same reasoning as
    CompositeChoiceModel's `_next_condition_ind`): removing one outcome must not renumber, and
    so break, the ids any other outcome's target is still stored under. Subclasses populate/
    mutate `self._outcomes` and must emit `outcomes_changed` whenever its key set changes shape
    (not on every settings change - only when an outcome is added or removed) - SwitchElt's
    BranchMixin listens for that to rebuild its targets/transitions, preserving ones that
    survive.
    """
    params = []
    model_name: str = abstract_attribute()
    outcomes_changed = QtCore.Signal()

    def __init__(self, parent_elt: 'SwitchElt'):
        QtCore.QObject.__init__(self)
        ParameterManager.__init__(self, settings_name='switch_model_settings',
                                  action_list=("search", "save", "update", "load"))
        self.parent_elt = parent_elt
        self.modules_manager: ModulesManager = parent_elt.modules_manager
        self._outcomes: dict[int, str] = {}

    def __eq__(self, other: 'SwitchModelBase') -> bool:
        return self.to_dict() == other.to_dict()

    def updated_module_manager(self):
        """ called whenever the parent modules manager is updated

        to be reimplemented
        """
        pass

    @property
    def outcomes(self) -> dict[int, str]:
        """ outcome id -> display label, in display order """
        return dict(self._outcomes)

    def execute(self, dte: DataToExport):
        self.parent_elt.go_to_signal.emit(self.evaluate(dte))

    def evaluate(self, dte: DataToExport) -> int:
        """ Compute and return which of self.outcomes' keys applies, without emitting
        go_to_signal.

        To be reimplemented
        """
        raise NotImplementedError

    def check_set_is_valid(self):
        """ Check if the current settings of this model are valid

        To be reimplemented

        Should raise ElementError if not valid
        """
        return None

    def to_dict(self) -> dict[str, Any]:
        """ adds attribute to a dict in order to produce a human readable
        representation/configuration for this model params

        to be reimplemented
        """
        return {}

    def from_dict(self, dict_config: dict[str, Any]):
        """ Create/set the custom part of the element to finish initialization
        using setters, attribute assignment or methods

        to be reimplemented
        """
        pass


def get_switch_models():
    """
    Register SwitchModels in pymodaq models entrypoints, mirroring
    choice_models.model.get_choice_models for SwitchModelBase instead of ChoiceModelBase.

    Returns
    -------
    list: list of dict containing the name and python module of the found models
    """
    main_model_path = Path(__file__).parent.parent.parent.joinpath('switch_models')
    for mod in pkgutil.iter_modules([str(main_model_path)]):
        try:
            importlib.import_module(f'pymodaq.extensions.sequencer.switch_models.{mod.name}')
            # by just importing the module, the models that may have a register decorator will be
            # added to the factory

        except Exception as e:  # pragma: no cover
            logger.warning(str(e))

    discovered_models = list(get_entrypoints(group='pymodaq.switch_models'))

    if len(discovered_models) > 0:
        for pkg in discovered_models:
            try:
                module = importlib.import_module(pkg.value)
                module_name = pkg.value

                for mod in pkgutil.iter_modules([str(Path(module.__file__).parent.joinpath('switch_models'))]):
                    try:
                        importlib.import_module(f'{module_name}.switch_models.{mod.name}', module)
                        # by just importing the module, the models that may have a register decorator will be
                        # added to the factory

                    except Exception as e:  # pragma: no cover
                        logger.warning(str(e))

            except Exception as e:  # pragma: no cover
                logger.warning(f'Impossible to import the {pkg.value} extension: {str(e)}')
