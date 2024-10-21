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

    def __init__(self, actuators: list = [], scanner_type: str = None):    
        QObject.__init__(self)
        self.actuators = actuators
        self.scanner_type = scanner_type

    @property
    def scanner_type(self,):
        return self._scanner_type
    
    @scanner_type.setter
    def scanner_type(self,scanner_type):
        self._scanner_type = scanner_type
        # self.updateScannerType()

    def get_indexing(self,shuffler=None):        
        pass

        indexing = [np.arange(self.scanners[act].n_steps) for act in self.ordering]
        indexing_array = np.array(list(product(*indexing)))                      
        return indexing_array
    
    def get_positions(self,shuffler=None):
        pass

        positions = [self.scanners[act].positions for act in self.ordering]
        positions_array = np.array(list(product(*positions)))      
        return positions_array    
    
    @property
    def positions(self,):
        #Function to access

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
    

class SequentialScanners(ScannerSelector):
    def __init__(self, actuators: list = [], scanner_type: str = 'sequential'):
        super().__init__(actuators, scanner_type)


    def makeScanner(self,act):
        scanner = sequential_scanner.SequentialScanner(self._scanners_settings_widget,actuator=act)
        scanner.updateScanner()                
        scanner.scanner_updated_signal.connect(self.updateGUI)    
        return scanner

    def removeScanner(self,act):
        scan = self.actuators.pop(act)          
        ind = self._scanners_settings_widget.layout().indexOf(scan.scanner_settings_widget)
        child = self._scanners_settings_widget.layout().takeAt(ind)
        child.widget().deleteLater()
        del(child)
        QtWidgets.QApplication.processEvents()
    
    # @actuators.setter
    # def actuators(self, act_list):
    #     """Definition of actuators, a dictionnary is made with actuators as keys and scanner object as values
    #     Args:
    #         act_list (list(DAQ_Move)): _description_
    #     """
    #     self._actuators.resized.disconnect(self.updateGUI)
    #     for act in self.actuators.copy(): #Loop through copy to avoid RuntimeError: OrderedDict mutated during iteration
    #         if act not in act_list:
    #             self.removeScanner(act)  
    #     for act in act_list:
    #         if act not in self.actuators:
    #             self.actuators[act] = self.makeScanner(act)     
    #     self.ordering = [act.title for act in self.actuators]
    #     self._actuators.resized.connect(self.updateGUI)

    #     self.updateParamTree()
    #     # self.updateGUI()


class GlobalScanners(ScannerSelector): 
    def __init__(self, actuators: list = [], scanner_type: str = 'global'):
        super().__init__(actuators, scanner_type)


    def set_scanner(self):
        try:
            self._scanner: ScannerBase = scanner_factory.get(self.settings['scan_type'],
                                                             self.settings['scan_sub_type'],
                                                             actuators=self.actuators)
            while True:
                child = self._scanner_settings_widget.layout().takeAt(0)
                if not child:
                    break
                child.widget().deleteLater()
                QtWidgets.QApplication.processEvents()

            self._scanner_settings_widget.layout().addWidget(self._scanner.settings_tree)
            self._scanner.settings.sigTreeStateChanged.connect(self._update_steps)

        except ValueError as e:
            pass

    @property
    def actuators(self):
        """list of str: Returns as a list the name of the selected actuators to describe the actual scan"""
        return self._actuators

    @actuators.setter
    def actuators(self, act_list):
        self._actuators = act_list
        self.set_scanner()