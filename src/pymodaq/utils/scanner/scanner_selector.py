from __future__ import annotations
from typing import Tuple, List, TYPE_CHECKING
from collections import OrderedDict

import numpy as np

from qtpy import QtWidgets, QtCore, QtGui
from qtpy.QtCore import QObject, Signal, Slot
from pymodaq.utils.managers.action_manager import ActionManager
from pymodaq.utils.logger import set_logger, get_module_name
from pymodaq.utils.config import Config
from pymodaq.utils.scanner.scan_factory import ScannerFactory, ScannerBase
from pymodaq.utils.managers.parameter_manager import ParameterManager, Parameter
import pymodaq.utils.daq_utils as utils
import pymodaq.utils.plotting.data_viewers.viewer1Dbasic as viewer

import pymodaq.utils.parameter.utils as putils
from pymodaq.utils.scanner.utils import ScanInfo
from pymodaq.utils.plotting.scan_selector import Selector
from pymodaq.utils.data import DataToExport, DataActuator
from itertools import permutations
if TYPE_CHECKING:
    from pymodaq.control_modules.daq_move import DAQ_Move


logger = set_logger(get_module_name(__file__))
config = Config()
scanner_factory = ScannerFactory()

class ScannerSelector(QObject,):                    
    """Main Object to define a PyMoDAQ scan and create a UI to set it

    Parameters
    ----------
    parent_widget: QtWidgets.QWidget
    scanner_items: list of GraphicItems
        used by ScanSelector for chosing scan area or linear traces
    actuators: List[DAQ_Move]
        list actuators names

    See Also
    --------
    ScanSelector, ScannerBase, TableModelSequential, TableModelTabular, pymodaq_types.TableViewCustom
    """
    scanner_updated_signal = Signal()
    settings_name = 'scanner'
    limTableSize = 500 #Threshold for displaying in table
    params = [
    ]

    def __init__(self, actuators: list = [], scanner_type: str = None):    
        QObject.__init__(self)
        if parent_widget is None:
            parent_widget = QtWidgets.QWidget()
        self.actuators = actuators
        self.scanner_type = scanner_type
        self._scanner: ScannerBase = scanner_factory.get(self.scanner_type,actuators=[self.actuator])   
        self.scanner.settings.sigTreeStateChanged.connect(self.updateDisplayWidget)

    @property
    def scanner_type(self,):
        return self._scanner_type
    
    @scanner_type.setter
    def scanner_type(self,scanner_type):
        self._scanner_type = scanner_type
        self.updateScannerType()

    @property
    def positions(self,):
        # import copy
        # positions = copy.deepcopy(np.squeeze(self.scanner.positions))    
        positions = np.squeeze(self.scanner.positions)    
        if self.is_action_checked('randomize_positions'):    
            rng = np.random.default_rng()
            numbers = rng.choice(len(positions), size=len(positions), replace=False)
            positions = positions[numbers]
            # np.random.shuffle(positions)
        if self.is_action_checked('backandforth'):        
            positions = np.concatenate([positions[0::2],np.flip(positions[1::2])])
        return positions
    
    @property    
    def axes_unique(self,):
        return self.scanner.axes_unique    
    
    @property
    def n_steps(self,):
        return self.scanner.n_steps
    
    @property
    def scanner(self) -> ScannerBase:        
        return self._scanner
                
    def updateScanner(self,):
        ind = self.scanner_settings_layout.indexOf(self.scanner.settings_tree)
        if ind:
            child = self.scanner_settings_layout.takeAt(ind)
            child.widget().deleteLater()
        self._scanner: ScannerBase = scanner_factory.get('Scan1D',self.scanType.currentText(),actuators=[self.actuator])  
        self.scanner.settings.sigTreeStateChanged.connect(self.scanner_updated_signal.emit)
        self.scanner_settings_layout.insertWidget(ind,self.scanner.settings_tree)
        self.scanner_updated_signal.emit()
        QtWidgets.QApplication.processEvents()        
