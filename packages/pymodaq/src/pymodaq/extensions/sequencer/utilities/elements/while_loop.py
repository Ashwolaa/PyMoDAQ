from typing import Any
import weakref

from qtpy import QtCore
from serializall import SerializableFactory

from pymodaq_data import DataToExport
from pymodaq_gui.managers.parameter_manager import ParameterTreeWidget
from pymodaq_gui.utils.widgets.combo import ComboBox

from pymodaq.utils.managers.modules_manager import ModulesManager
from pymodaq.extensions.sequencer.utilities.choice_models.model import ChoiceModelBase
from pymodaq.extensions.sequencer.utilities.choice_models.factory import ChoiceModelFactory
from pymodaq.extensions.sequencer.utilities.element_factory import SeqEltFactory
from pymodaq.extensions.sequencer.utilities.elements.group import GroupElt
from pymodaq.extensions.sequencer.utilities.widget_with_toolbar import WidgetWithToolbar


choice_factory = ChoiceModelFactory()


@SerializableFactory.register_decorator()
@SeqEltFactory.register_elt()
class WhileElt(GroupElt):
    """ A condition-driven loop: runs its children repeatedly while a condition evaluates True,
    finishes once it evaluates False.

    A GroupElt whose "run once" becomes "run while this condition holds" - this is the
    "while True: repeat this action" primitive, sibling to RepeatElt (which counts instead).
    The condition reuses the same pluggable ChoiceModel abstraction as ChoiceElt
    (true/false/threshold/user_input/composite), just evaluated directly each pass instead of
    driving a go_to_true/go_to_false branch.
    """
    elt_name = 'while'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modules_manager = ModulesManager()
        self._choice_model: ChoiceModelBase = None

    def do_things_with_dashboard(self):
        self.dashboard.experiment_manager.applied_entry.connect(self.update_modules)
        self.update_modules()

    def update_modules(self):
        self.modules_manager.detectors_all = self.dashboard.modules_manager.detectors_all
        self.modules_manager.selected_detectors_name = [det.title for det in self.dashboard.modules_manager.detectors_all]
        self.modules_manager.actuators_all = self.dashboard.modules_manager.actuators_all
        self.modules_manager.selected_actuators_name = [act.title for act in self.dashboard.modules_manager.actuators_all]
        self.choice_model.updated_module_manager()

    @property
    def choice_model(self) -> ChoiceModelBase:
        if self._choice_model is None:
            self.choice_model = choice_factory.models[0]
        return self._choice_model

    @choice_model.setter
    def choice_model(self, value: str):
        self._choice_model = choice_factory.get_model(value)(self)

    @QtCore.Slot(str)
    def set_choice_model(self, value: str):
        self.choice_model = value

    def _create_widget(self, base_widget: WidgetWithToolbar) -> WidgetWithToolbar:
        base_widget = super()._create_widget(base_widget)
        combo = ComboBox()
        with QtCore.QSignalBlocker(combo):
            combo.addItems(choice_factory.models)
            combo.setCurrentText(self.choice_model.model_name)
            combo.currentTextChanged.connect(self.set_choice_model)
            combo.setToolTip('Loop while this condition evaluates True')
        base_widget.insert_widget(combo, 1)

        parameter_tree = ParameterTreeWidget()
        parameter_tree.tree.setParameters(self.choice_model.settings, showTop=False)
        self.param_tree_widget = weakref.ref(parameter_tree)
        parameter_tree.tree.setMinimumHeight(len(self.choice_model.settings.children()) * 50)
        combo.currentTextChanged.connect(lambda: self.update_params(parameter_tree))
        base_widget.insert_widget(parameter_tree.widget, 2)
        base_widget.tree = parameter_tree
        parameter_tree.widget.setVisible(len(self.choice_model.params) != 0)
        return base_widget

    def update_params(self, param: ParameterTreeWidget):
        param.widget.setVisible(len(self.choice_model.params) != 0)
        param.tree.setParameters(self.choice_model.settings, showTop=False)
        param.tree.setMinimumHeight(len(self.choice_model.settings.children()) * 50)

    def _execute(self, dte: DataToExport = None):
        if self.choice_model.evaluate(dte):
            self.children_signal.emit()
        else:
            self.done_signal.emit()

    def to_dict_custom(self) -> dict[str, Any]:
        """ adds attribute to a dict in order to produce a human readable
        representation/configuration for this element

        to be reimplemented
        """
        dict_config = super().to_dict_custom()
        dict_config['choice_model'] = self.choice_model.model_name
        dict_config.update(self.choice_model.to_dict())
        return dict_config

    def from_dict_custom(self, dict_config: dict[str, Any]):
        """ Create/set the custom part of the element to finish initialization
        using setters, attribute assignment or methods
        """
        super().from_dict_custom(dict_config)
        self.choice_model = dict_config.pop('choice_model')
        self.choice_model.from_dict(dict_config)

    def _eq(self, other: 'WhileElt'):
        """ Custom method to reimplement to assert two elements are equals"""
        if not hasattr(other, 'choice_model'):
            return False
        return super()._eq(other) and self.choice_model == other.choice_model

    def __repr__(self):
        return f'{super().__repr__()} - while {self.choice_model.model_name}'

    def check_set_is_valid(self):
        """ Check the validity of the element

        Will be called before executing the element. Try to make sure the element is valid or raise
        ElementError if the user may do something!
        """
        super().check_set_is_valid()
        self.choice_model.check_set_is_valid()
