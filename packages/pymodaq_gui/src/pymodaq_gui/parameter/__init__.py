from qtpy import QtWidgets, QtCore, QtGui

from pyqtgraph.parametertree import parameterTypes, Parameter, ParameterTree
from . import pymodaq_ptypes
from pymodaq_gui.utils.styling import create_icon

class ParameterTree(ParameterTree):
    """PyMoDAQ's ParameterTree.

    Extends the pyqtgraph base with:

    * Consistent header behaviour.
    * :attr:`expose_requested` signal — emitted when the user picks a
      "Set as…" entry on a parameter that the DAQ layer has marked with a
      ``context`` opt.  The DAQ code sets :meth:`set_param_role` in response
      to display a joystick or videocam icon in column 0.
    * :meth:`set_param_role` / :meth:`set_param_icon` for column-0 icons.
    * Nested context menus: set a parameter's ``context`` opt to a nested
      dict (``{"submenu": {"action": None}}``) to get a submenu in the
      ctrl-button and right-click menus (handled natively by the fork's
      ``build_menu_from_iterable`` in ``_buildParamMenu``).
    """

    #: Emitted when the user picks a "Set as…" entry via a param's ``context`` opt.
    #: Carries ``(param: Parameter, role: str)``.
    #: The DAQ layer connects this after marking plugin params with context actions.
    expose_requested = QtCore.Signal(object, str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._param_roles: dict[int, str] = {}   # id(param) -> role_key

        self.header().setVisible(True)
        self.header().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

    def set_param_role(self, param, role) -> None:
        """Mark *param* as bound to *role* and update its column-0 icon.

        Parameters
        ----------
        param:
            The parameter to update.
        role:
            ``'move'`` (joystick icon) or ``'viewer'`` (videocam icon),
            or ``None`` to clear the binding and remove the icon.
        """
        key = id(param)
        if role is None:
            self._param_roles.pop(key, None)
            icon = QtGui.QIcon()
        else:
            self._param_roles[key] = role
            _, icon_name = self.CAPABILITY_ROLES.get(role, (None, None))
            icon = create_icon(icon_name) if icon_name else QtGui.QIcon()

        for item in param.items:
            # Group parameters put a QWidget in column 0 (add-button row).
            # Setting an icon on those items would discard that widget for
            # the whole subtree — skip them.
            if self.itemWidget(item, 0) is not None:
                continue
            item.setIcon(0, icon)

    def set_param_icon(self, param, icon) -> None:
        """Set a display icon on *param*'s column-0 cell.

        This is a lower-level companion to :meth:`set_param_role`.  Use it
        when you want full control over the icon without going through the
        role system.

        The same update can be triggered via the parameter's own opts
        (``'display_icon'`` — note: ``'icon'`` is reserved by pyqtgraph's
        action parameter type)::

            param.setOpts(display_icon='gear2')     # string → icon library
            param.setOpts(display_icon=my_qicon)    # QIcon passthrough
            param.setOpts(display_icon=None)        # clear

        Parameters
        ----------
        param:
            The parameter whose column-0 icon should be updated.
        icon:
            A ``QIcon``, a string name looked up in the pymodaq icon library,
            or ``None`` to clear the current icon.
        """
        resolved = create_icon(icon)
        param.setOpts(icon=resolved)
