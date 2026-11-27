import pytest
import qt_themes
from qtpy import QtCore, QtGui, QtWidgets

from pymodaq_gui.managers.manager_base import ManagerSubEntriesModel
from pymodaq_gui.utils.status_palette import Status, StatusPalette


@pytest.mark.parametrize('theme', ['catppuccin_latte', 'catppuccin_mocha'])
def test_subentries_foreground_follows_status_palette(qtbot, theme):
    app = QtWidgets.QApplication.instance()
    previous, palette = qt_themes.get_theme(), QtGui.QPalette(app.palette())
    qt_themes.set_theme(theme, style=None)
    try:
        model = ManagerSubEntriesModel(['off', 'idle', 'error'])
        model.set_status(1, True)
        model.set_status(2, False)
        for row, status in enumerate((Status.OFF, Status.IDLE, Status.ERROR)):
            brush = model.data(model.index(row, 0), QtCore.Qt.ItemDataRole.ForegroundRole)
            assert brush.color() == StatusPalette.color(status)
            assert model.colors[row] == StatusPalette.color(status)
    finally:
        qt_themes.set_theme(previous, style=None)
        app.setPalette(palette)
