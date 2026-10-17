from typing import Callable

from pymodaq.extensions.sequencer.utilities.switch_models.model import SwitchModelBase
from pymodaq_utils.logger import set_logger, get_module_name


logger = set_logger(get_module_name(__file__))


class SwitchModelFactory:
    """The factory class to get SwitchModels to be used with SwitchElt

    Separate registry from ChoiceModelFactory (see SwitchModelBase docstring) - a "which band"
    model and a "true/false" model showing up mixed in one picker would be confusing, and most
    wouldn't work with both binary and N-way elements anyway.
    """

    models_registry = {}

    @classmethod
    def register_switch(cls) -> Callable:
        """Class decorator method to register Models to be used with the Switch Element class
        to the internal registry.
        Must be used as a decorator above the definition of a SwitchModelBase inherited class.

        The class must implement the SwitchModelBase interface
        """

        def inner_wrapper(wrapped_class: type[SwitchModelBase]) -> type[SwitchModelBase]:
            model_name = wrapped_class.model_name

            if model_name not in cls.models_registry:
                cls.models_registry[model_name] = wrapped_class
            else:
                logger.info(f"Switch model {model_name} already registered")
            return wrapped_class

        return inner_wrapper

    @classmethod
    def get_model(cls, name: str) -> type[SwitchModelBase]:
        """Factory command to get registered subentry handler.

        This method gets the appropriate executor class from the registry
        """

        if name not in cls.models_registry:
            raise KeyError(f"{name} is not a supported switch model.")

        return cls.models_registry[name]

    @property
    def models(self) -> list[str]:
        return [model for model in self.models_registry.keys()]
