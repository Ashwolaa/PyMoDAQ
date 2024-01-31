from __future__ import annotations
from typing import Tuple, List, TYPE_CHECKING
from collections import OrderedDict

import numpy as np

from qtpy import QtWidgets, QtCore, QtGui
from qtpy.QtCore import QObject, Signal, Slot

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

class ScannerContainer(QObject, ParameterManager):                    
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
    params = [
    ]

    def __init__(self, parent_widget: QtWidgets.QWidget = None, actuator= None, scanner_type: str = None
                 ):    
        QObject.__init__(self)
        ParameterManager.__init__(self)        
        if parent_widget is None:
            parent_widget = QtWidgets.QWidget()
        self.parent_widget = parent_widget
        self.scanner_settings_widget = None
        self._scanner: ScannerBase = None
        self.actuator = actuator
        self.setup_ui()
        
    def setup_ui(self):
        self.scanner_settings_widget = QtWidgets.QWidget()
        self.scanner_settings_layout =QtWidgets.QVBoxLayout()
        self.scanner_settings_widget.setLayout(self.scanner_settings_layout)
        self.scanner_settings_layout.setContentsMargins(0, 0, 0, 0)
        self.parent_widget.layout().addWidget(self.scanner_settings_widget)            
        
        label = QtWidgets.QLabel()
        label.setText(self.actuator.title)
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
        self.scanType.currentIndexChanged.connect(self.makeScanner)                        
        widget.layout().addWidget(self.scanType)        
        self.randomizeScan = QtWidgets.QCheckBox('Randomize')
        widget.layout().addWidget(self.randomizeScan)        

        self.scanner_settings_layout.addWidget(widget)                        


        widget = QtWidgets.QWidget()
        widget.setLayout(QtWidgets.QHBoxLayout())            

        label = QtWidgets.QLabel()
        label.setText('Display')
        widget.layout().addWidget(label)
                   
        self.displayViewer_cb = QtWidgets.QCheckBox('show graph')        
        self.displayViewer_cb.stateChanged.connect(self.showViewer)
        widget.layout().addWidget(self.displayViewer_cb)

        self.displayTable_cb = QtWidgets.QCheckBox('show table')        
        self.displayTable_cb.stateChanged.connect(self.showTable)       
        widget.layout().addWidget(self.displayTable_cb)
         
        self.scanner_settings_layout.addWidget(widget)                                
                        
        # self.makeScanner()
        
    def showTable(self,):
        if self.displayTable_cb.isChecked():
            self.displayTable.show()
        else:
            self.displayTable.hide()
        
    def showViewer(self,):      
        if self.displayViewer_cb.isChecked():
            self.displayViewer.parent.show()
        else:
            self.displayViewer.parent.hide()             
                
    def makeViewer(self,):
        positions = np.squeeze(self.scanner.positions)
        displayViewer = viewer.Viewer1DBasic(QtWidgets.QWidget())                
        displayViewer.show_data([positions])
        displayViewer.update_labels(labels=[self.actuator.title])
        displayViewer.set_axis_label(axis_settings=dict(orientation='bottom', label='Steps', units=''))
        displayViewer.set_axis_label(axis_settings=dict(orientation='left', label='Positions', units=''))   
        displayViewer.parent.setVisible(self.displayViewer_cb.isChecked()) 
            
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
        displayTable.setVisible(self.displayTable_cb.isChecked()) 
        return displayTable
    
    def makeDisplayWidget(self,):    
        if self.scanner_settings_layout.count() == 5:
            child = self.scanner_settings_layout.takeAt(self.scanner_settings_layout.count()-1)
            child.widget().deleteLater()                
        self.displayWidget = QtWidgets.QWidget()
        self.displayLayout = QtWidgets.QHBoxLayout()                
        self.displayViewer = self.makeViewer()        
        self.displayLayout.addWidget(self.displayViewer.parent)       
        self.displayTable = self.makeTable()           
        self.displayLayout.addWidget(self.displayTable)
        self.displayWidget.setLayout(self.displayLayout)   
        self.displayWidget.show()
        self.scanner_settings_layout.addWidget(self.displayWidget)                         
                

    def updateDisplayWidget(self,):
        positions = np.squeeze(self.scanner.positions)        
        self.displayTable.setRowCount(len(positions))        
        for ind,pos in enumerate(positions):
            step_item = QtWidgets.QTableWidgetItem(str(ind))
            step_item.setFlags(step_item.flags() & ~QtCore.Qt.ItemIsEditable)
            pos_item = QtWidgets.QTableWidgetItem(str(pos))
            pos_item.setFlags(pos_item.flags() & ~QtCore.Qt.ItemIsEditable)            
            self.displayTable.setItem(ind,0,step_item)
            self.displayTable.setItem(ind,1,pos_item)  
        self.displayTable.resizeColumnsToContents()                
        self.displayViewer.show_data([positions])
            
    
    @property
    def scanner(self) -> ScannerBase:        
        return self._scanner
                
    def makeScanner(self,):
        while self.scanner_settings_layout.count() != 3:
            child = self.scanner_settings_layout.takeAt(self.scanner_settings_layout.count()-1)
            child.widget().deleteLater()
    
        self._scanner: ScannerBase = scanner_factory.get('Scan1D',self.scanType.currentText(),actuators=[self.actuator])   
        self.scanner_settings_layout.addWidget(self.scanner.settings_tree)
        self.scanner.settings.sigTreeStateChanged.connect(self.updateDisplayWidget)
        self.makeDisplayWidget()
        self.scanner_settings_layout.addWidget(self.displayWidget)                         
        QtWidgets.QApplication.processEvents()
        