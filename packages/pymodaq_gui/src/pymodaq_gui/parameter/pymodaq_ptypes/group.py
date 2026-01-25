from qtpy import QtWidgets
from pyqtgraph.parametertree.parameterTypes.basetypes import GroupParameter, GroupParameterItem

from pymodaq_gui.utils.menu_builder import build_nested_menu

class GroupParameterItem(GroupParameterItem):
    """
    Group parameters are used mainly as a generic parent item that holds (and groups!) a set
    of child parameters. It also provides a simple mechanism for displaying a button or combo
    that can be used to add new parameters to the group.
    """

    def __init__(self, param, depth):
        if 'addMenu' in param.opts:
            param.opts.pop('addList', None)
        super().__init__(param, depth)

        if 'addMenu' in param.opts:
            # Disconnect signal from previous init
            self.addWidget.clicked.disconnect(self.addClicked)
            # Create the nested menu
            self.addMenu = QtWidgets.QMenu(self.addWidget)
            self.addWidget.setMenu(self.addMenu)
            # Populate the nested menu structure
            self.updateAddMenu()    

        self.optsChanged(self.param, self.param.opts)
             
    def optsChanged(self, param, opts):
        super().optsChanged(param, opts)

        if 'addMenu' in opts and hasattr(self,'addMenu'):
            self.updateAddMenu()            

    def updateAddMenu(self):
        self.addWidget.blockSignals(True)
        try:
            self.addMenu.clear()
            addMenu = self.param.opts.get('addMenu', [])
            build_nested_menu(self.addMenu, addMenu, self._add_menu_item_selected)
        finally:
            self.addWidget.blockSignals(False)

    def _add_menu_item_selected(self, path_tuple):
        """Called when a menu item is selected from the nested add menu
        The parameter MUST have an 'addNew' method defined.
        """
        # Call the parameter's addNew method with the selected type
        self.param.addNew(path_tuple)
        # Reset the button text back to the original addText
        # (equivalent to setCurrentIndex(0) for the combo)
        if hasattr(self.param.opts, 'addText'):
            self.addWidget.setText(self.param.opts['addText'])

class GroupParameter(GroupParameter):
    
    itemClass = GroupParameterItem

    def __init__(self, **opts):
        super().__init__(**opts)
   