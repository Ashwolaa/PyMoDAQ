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

class ScannerSelector(QObject, ParameterManager,ActionManager):                    
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

    def __init__(self, parent_widget: QtWidgets.QWidget = None, actuator= None, scanner_type: str = None
                 ):    
        QObject.__init__(self)
        ParameterManager.__init__(self)    
        ActionManager.__init__(self,toolbar=QtWidgets.QToolBar())       
        self.setup_actions()
        if parent_widget is None:
            parent_widget = QtWidgets.QWidget()
        self.parent_widget = parent_widget
        self.scanner_settings_widget = None
        self.actuator = actuator
        self._scanner: ScannerBase = scanner_factory.get('Scan1D','Linear',actuators=[self.actuator])   
        self.setup_ui()

        self.scanner.settings.sigTreeStateChanged.connect(self.updateDisplayWidget)


        
    def setup_ui(self):
        self.scanner_settings_widget = QtWidgets.QWidget()
        self.scanner_settings_layout =QtWidgets.QVBoxLayout()
        self.scanner_settings_widget.setLayout(self.scanner_settings_layout)
        self.scanner_settings_layout.setContentsMargins(0, 0, 0, 0)
        self.parent_widget.layout().addWidget(self.scanner_settings_widget)            
        
        label = QtWidgets.QLabel()
        label.setText(f'{self.actuator.title}')
        label.setStyleSheet("font-weight: bold")
        label.setAlignment(QtCore.Qt.AlignCenter)
        self.scanner_settings_layout.addWidget(label)
        
        widget = QtWidgets.QWidget()
        widget.setLayout(QtWidgets.QHBoxLayout())        

        
        label = QtWidgets.QLabel()
        label.setText('Scan type')
        widget.layout().addWidget(label)
        
        self.scanType = QtWidgets.QComboBox()
        self.scanType.addItems(scanner_factory.scan_sub_types(scanner_factory.scan_types()[0]))
        self.scanType.currentIndexChanged.connect(self.updateScanner)                        
        widget.layout().addWidget(self.scanType)        
  
        widget.layout().addWidget(self.toolbar)        

        self.scanner_settings_layout.addWidget(widget)                        

        self.scanner_settings_layout.addWidget(self.scanner.settings_tree)

        self.makeDisplayWidget()
        self.scanner_settings_layout.addWidget(self.displayWidget)                         
                        
        # self.makeScanner()
        
    def showTable(self,):
        if self.is_action_checked('show_table'):        
            self.displayTable.show()
        else:
            self.displayTable.hide()
        
    def showViewer(self,):      
        if self.is_action_checked('show_positions'):
            self.displayViewer.parent.show()
        else:
            self.displayViewer.parent.hide()             
                
    def makeViewer(self,):
        self.displayViewer_widget = QtWidgets.QWidget()
        displayViewer = viewer.Viewer1DBasic(self.displayViewer_widget)                
        displayViewer.show_data([self.positions])
        displayViewer.update_labels(labels=[self.actuator.title])
        displayViewer.set_axis_label(axis_settings=dict(orientation='bottom', label='Steps', units=''))
        displayViewer.set_axis_label(axis_settings=dict(orientation='left', label='Positions', units=''))   
        displayViewer.parent.setVisible(self.is_action_checked('show_positions'))             
        return displayViewer
    
    
    def makeTable(self,):        
        positions = np.squeeze(self.scanner.positions)
        displayTable = QtWidgets.QTableWidget()
        displayTable.setColumnCount(2)
        displayTable.setRowCount(len(positions))        
        displayTable.setHorizontalHeaderLabels(['Steps','Positions'])
        displayTable.verticalHeader().hide()
        for ind,pos in enumerate(positions):
            step_item = QtWidgets.QTableWidgetItem(str(ind))
            step_item.setFlags(step_item.flags() & ~QtCore.Qt.ItemIsEditable)
            pos_item = QtWidgets.QTableWidgetItem(str(pos))
            pos_item.setFlags(pos_item.flags() & ~QtCore.Qt.ItemIsEditable)            
            displayTable.setItem(ind,0,step_item)
            displayTable.setItem(ind,1,pos_item)                       
        displayTable.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        displayTable.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        displayTable.resizeColumnsToContents()        
        displayTable.setMaximumWidth(displayTable.horizontalHeader().length() + 
                         displayTable.verticalHeader().width())   
        displayTable.setVisible(self.is_action_checked('show_table')) 
        return displayTable
    
    def updateTable(self,):
        if self.n_steps>self.limTableSize:            
            self.displayTable.setRowCount(self.limTableSize)
        else:
            self.displayTable.setRowCount(self.n_steps)

        for ind,pos in enumerate(self.positions[:self.limTableSize]):
                step_item = QtWidgets.QTableWidgetItem(str(ind))
                step_item.setFlags(step_item.flags() & ~QtCore.Qt.ItemIsEditable)
                pos_item = QtWidgets.QTableWidgetItem(str(pos))
                pos_item.setFlags(pos_item.flags() & ~QtCore.Qt.ItemIsEditable)            
                self.displayTable.setItem(ind,0,step_item)
                self.displayTable.setItem(ind,1,pos_item)  
        self.displayTable.resizeColumnsToContents()          

    def updateViewer(self,):
        self.displayViewer.show_data([self.positions])

    def setup_actions(self):
        self.add_action('show_positions', 'Show positions', '2d', 'Display positions on a graphic', checkable=True)
        self.connect_action('show_positions', self.showViewer)
        self.add_action('show_table', 'Table of positions', 'Calculator', 'Display positions in a table', checkable=True)
        self.connect_action('show_table', self.showTable)
        self.add_action('randomize_positions','Randomize', checkable=True)
        self.add_action('backandforth','Back and forth', checkable=True)


    def makeDisplayWidget(self,):      
        self.displayWidget = QtWidgets.QWidget()
        self.displayLayout = QtWidgets.QHBoxLayout()  
        self.displayWidget.setLayout(self.displayLayout)   
        self.displayViewer = self.makeViewer()        
        self.displayTable = self.makeTable()
        self.displayLayout.addWidget(self.displayViewer_widget)       
        self.displayLayout.addWidget(self.displayTable)
                

    def updateDisplayWidget(self,):
        self.updateTable()
        self.updateViewer()

    @property
    def positions(self,):
        return np.squeeze(self.scanner.positions)    
    
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
        self.scanner.settings.sigTreeStateChanged.connect(self.updateDisplayWidget)
        self.updateDisplayWidget()
        self.scanner_settings_layout.insertWidget(ind,self.scanner.settings_tree)
        QtWidgets.QApplication.processEvents()        
