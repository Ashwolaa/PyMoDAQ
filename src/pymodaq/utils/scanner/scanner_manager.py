from __future__ import annotations
from typing import Tuple, List, TYPE_CHECKING
from collections import OrderedDict


from qtpy import QtWidgets, QtCore
from qtpy.QtCore import QObject, Signal, Slot

from pymodaq.utils.QObjects.list import SignalList
from pymodaq.utils.QObjects.dict import SignalDict,SignalOrderedDict

from pymodaq.utils.logger import set_logger, get_module_name
from pymodaq.utils.config import Config
from pymodaq.utils.array_manipulation import makeSnake
from pymodaq.utils.scanner import scanner_selector,sequential_scanner
from pymodaq.utils.scanner.scan_factory import ScannerFactory, ScannerBase
from pymodaq.utils.managers.parameter_manager import ParameterManager, Parameter
import pymodaq.utils.daq_utils as utils
import pymodaq.utils.parameter.utils as putils
from pymodaq.utils.scanner.utils import ScanInfo
from pymodaq.utils.plotting.scan_selector import Selector
from pymodaq.utils.data import DataToExport, DataActuator
from itertools import permutations,product
from pymodaq.utils.data import Axis, DataDistribution

import numpy as np
if TYPE_CHECKING:
    from pymodaq.control_modules.daq_move import DAQ_Move


logger = set_logger(get_module_name(__file__))
config = Config()
scanner_factory = ScannerFactory()


class ScannerManager(QObject, ParameterManager):                    
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
        {'title': 'Scan parameters:', 'name': 'scan_parameters', 'type': 'group',
         'children':[
            {'title': 'Scan dimension:', 'name': 'scan_dim', 'type': 'str',
         'readonly':True,},       
            {'title': 'Scan creation:', 'name': 'scan_type', 'type': 'list',
         'limits': ['sequential','global'],'tip':'Sequential: Actuator''s position are set up one at a time;\n Global: Actuator''s positions are set up all at a time'},               
            {'title': 'Ordering:', 'name': 'ordering', 'type': 'list',
         'limits': [],},
            {'title': 'Shuffling:', 'name': 'shuffling', 'type': 'list',
         'limits': ['Normal','Snake','Spiral'],'tooltip': 'Defines how the scan goes:'},
        {'title': 'N steps:', 'name': 'n_steps', 'type': 'int', 'value': 0, 'readonly': True},          
         ]},
        {'title': 'Show positions', 'name': 'show_positions', 'type': 'action'},
        {'title': 'Save scan settings', 'name': 'save_scan', 'type': 'action'},

    ]
    limTableSize = 500 #Threshold for displaying in table

    def __init__(self, parent_widget: QtWidgets.QWidget = None, scanner_items=OrderedDict([]),
                 actuators: List[DAQ_Move] = [], ordering: Tuple = ()):
        QObject.__init__(self)
        ParameterManager.__init__(self,action_list=())

        if parent_widget is None:
            parent_widget = QtWidgets.QWidget()
        self.parent_widget = parent_widget

        # self._scanners_settings_widget = None      


        # self._actuators = SignalDict()
        # self._actuators.resized.connect(self._update_steps)
        # self._scanners = SignalOrderedDict()
        # self._scanners.resized.connect(self._update_steps)

        # for act in actuators:


        self._actuators = SignalOrderedDict()
        self._actuators.resized.connect(self.updateGUI)

        self.ordering = None
        self.setup_ui()
        self.actuators = actuators

        self.settings.child('show_positions').sigActivated.connect(self.showTable)

    def updateGUI(self,):
        self.scanner_updated_signal.emit()
        return 0                

    def setup_ui(self):        
        self.parent_widget.setLayout(QtWidgets.QVBoxLayout())
        self.parent_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.parent_widget.layout().addWidget(self.settings_tree)
        self._scanners_settings_widget = QtWidgets.QWidget()
        self._scanners_settings_widget.setLayout(QtWidgets.QHBoxLayout())
        self._scanners_settings_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.parent_widget.layout().addWidget(self._scanners_settings_widget)
        self.settings_tree.setMinimumHeight(110)
        self.settings_tree.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.makeTable()
        self.scanner_updated_signal.connect(self.updateTable)
        self.scanner_updated_signal.connect(self._update_steps)



    def updateParamTree(self,):
        titles = [actuator.title for actuator in self.actuators]
        lim = []
        for perm in list(permutations(range(0,len(titles)))): 
            lim.append(list(titles[ind] for ind in perm))    
        self.settings.child('scan_parameters','ordering').setLimits(lim)        
        self.settings.child('scan_parameters','scan_dim').setValue(f'{len(titles)}D')   


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

    def value_changed(self, param: Parameter):        
        if param.name() == 'ordering':
            self.updateOrdering()
            self.scanner_updated_signal.emit()
        elif param.name() == 'show_positions':
            self.displayPositions()          
        elif param.name() == 'scan_type':
            if 'scan_type' == 'global':
                pass
            elif 'scan_type' == 'sequential':     
                pass

    def makeSnake2D(self,arr,L1,L2):
        for i in range(L1//2): 
            start = (2*i+1)*L2 
            end = start+L2-1
            arr[[start,end]] = arr[[end,start]]
        return arr

    def get_indexing(self,shuffler=None):        
        indexing = [np.arange(self.scanners[act].n_steps) for act in self.ordering]
        indexing_array = np.array(list(product(*indexing)))                      
        return indexing_array
    def get_positions(self,shuffler=None):
        positions = [self.scanners[act].positions for act in self.ordering]
        positions_array = np.array(list(product(*positions)))      
        return positions_array    
    
    # def displayPositions(self,):
    #     # positions_array = self.get_positions()
    #     # L_steps = len(positions_array)
    #     # all_indexing = np.array(list(itertools.product(*indexing)))  
    #     # makeSnake(all_indexing,L_index)                                
    #     # all_indexing = np.reshape(all_indexing,[L_index[0],L_index[1]*L_index[2],3])
    #     # for i,index in enumerate(all_indexing):
    #     #     if i%2:
    #     #         all_indexing[i] = np.flipud(all_indexing[i])            
    #     #     all_indexing[i] = makeSnake2D(self,all_indexing[i],L_index[1],L_index[2])        
    #     # # [0,1;0,2;0,3;1,1;1,2;1,3;2,1;2,2;2,3] ==) [0,1;0,2;0,3;1,3;1,2;1,1;2,1;2,2;2,3]
    #     self.updateTable()

    def makeTable(self,):        
        self.displayTable = QtWidgets.QTableWidget()       
        self.displayTable.verticalHeader().hide()                   
        self.displayTable.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        self.displayTable.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.displayTable.resizeColumnsToContents()

    def updateTable(self,):
        positions_array = self.get_positions()
        L_steps = len(positions_array)
        if L_steps>self.limTableSize:       
            self.displayTable.setRowCount(self.limTableSize)                
        else:
            self.displayTable.setRowCount(L_steps)                
        self.displayTable.setColumnCount(1+len(self.scanners))   
        self.displayTable.setHorizontalHeaderLabels(['Steps']+[f'{act}' for act in self.ordering])
        for ind,positions in enumerate(positions_array[:self.limTableSize]):
            step_item = QtWidgets.QTableWidgetItem(str(ind))
            step_item.setFlags(step_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.displayTable.setItem(ind,0,step_item)           
            for ind_pos,pos in enumerate(positions):
                pos_item = QtWidgets.QTableWidgetItem(str(pos))
                pos_item.setFlags(pos_item.flags() & ~QtCore.Qt.ItemIsEditable)            
                self.displayTable.setItem(ind,ind_pos+1,pos_item)   

    def showTable(self,):
        self.displayTable.show()
        self.displayTable.resizeColumnsToContents()               

    def updateOrdering(self,):      
        l1 = self.settings.child('scan_parameters','ordering').value()            
        if l1 and l1 != self.ordering:            
            child = dict()            
            for act in self.ordering:
                child[act] = self._scanners_settings_widget.layout().takeAt(0)
            for act in l1:                    
                    self._scanners_settings_widget.layout().addWidget(child[act].widget()) 
            self.ordering = l1
        self.scanner_updated_signal.emit()

    @property
    def scanner(self,act):
        return self.actuators[act].scanner

    @property
    def scanners(self,):
        """dict of scans: Returns as a dict the selected scanners that will make the actual scan"""
        scanners = {key.title: scans for key,scans in self.actuators.items()}
        return scanners
        
    @property
    def actuators(self,):
        """dict of actuators: Returns as a dict the name of the selected actuators to describe the actual scan"""
        return self._actuators

    @actuators.setter
    def actuators(self, act_list):
        """Definition of actuators, a dictionnary is made with actuators as keys and scanner object as values
        Args:
            act_list (list(DAQ_Move)): _description_
        """
        self._actuators.resized.disconnect(self.updateGUI)
        for act in self.actuators.copy(): #Loop through copy to avoid RuntimeError: OrderedDict mutated during iteration
            if act not in act_list:
                self.removeScanner(act)  
        for act in act_list:
            if act not in self.actuators:
                self.actuators[act] = self.makeScanner(act)     
        self.ordering = [act.title for act in self.actuators]
        self._actuators.resized.connect(self.updateGUI)

        self.updateParamTree()
        # self.updateGUI()


    def get_scan_info(self) -> ScanInfo:
        """Get a summary of the configured scan as a ScanInfo object"""
        return ScanInfo(self._scanner.n_steps, positions=self._scanner.positions,
                        axes_indexes=self._scanner.axes_indexes, axes_unique=self._scanner.axes_unique,
                        selected_actuators=[act.title for act in self.actuators])

    def get_nav_axes(self) -> List[Axis]:
        return [scan.get_nav_axes()[0] for scan in self.scanners.values()]     


    def get_scan_shape(self):
        return tuple([len(scan.axes_unique) for scan in self.scanners.values()])

    def get_indexes_from_scan_index(self, scan_index: int) -> Tuple[int]:
        """To be reimplemented. Calculations of indexes within the scan"""
        return self._scanner.get_indexes_from_scan_index(scan_index)

    def _update_steps(self):
        self.settings.child('scan_parameters','n_steps').setValue(self.tot_steps)                     

    @property
    def steps(self):
        return [scan.n_steps for scan in self.scanners.values()]     

    @property
    def tot_steps(self):
        return np.prod(self.steps)

    @property
    def n_axes(self):        
        return len(self.scanners)

    @property
    def positions(self):
        return self.get_positions()
      
    def positions_at(self, index: int) -> DataToExport:
        """ Extract the actuators positions at a given index in the scan as a DataToExport of DataActuators"""
        dte = DataToExport('scanner')
        for ind, pos in enumerate(self.positions[index]):
            dte.append(DataActuator(self.actuators[ind].title, data=float(pos)))
        return dte

    @property
    def axes_indexes(self):
        return self._scanner.axes_indexes
    
    @property
    def axes_unique(self):
        return [scan.axes_unique for scan in self.scanners]     

    @property
    def distribution(self):
        return self._scanner.distribution

    def set_scan(self):
        """Process the settings options to calculate the scan positions

        Returns
        -------
        bool: True if the processed number of steps if **higher** than the configured number of steps
        """
        oversteps = config('scan', 'steps_limit')
        if self._scanner.evaluate_steps() > oversteps:
            return True
        self._scanner.set_scan()
        self.settings.child('n_steps').setValue(self.n_steps)
        self.scanner_updated_signal.emit()
        return False

    def update_from_scan_selector(self, scan_selector: Selector):
        self._scanner.update_from_scan_selector(scan_selector)


def main():
    from pymodaq.utils.parameter import ParameterTree
    app = QtWidgets.QApplication(sys.argv)

    class MoveMock:
        def __init__(self, ind: int = 0):
            self.title = f'act_{ind}'
            self.units = f'units_{ind}'

    actuators = [MoveMock(ind) for ind in range(4)]

    params = [{'title': 'Actuators', 'name': 'actuators', 'type': 'itemselect',
               'value': dict(all_items=[act.title for act in actuators], selected=[]),'checkbox':True},
              {'title': 'Set Scan', 'name': 'set_scan', 'type': 'action'},
              ]
    settings = Parameter.create(name='settings', type='group', children=params)
    settings_tree = ParameterTree()
    settings_tree.setParameters(settings)

    widget_main = QtWidgets.QWidget()
    widget_main.setLayout(QtWidgets.QVBoxLayout())
    #widget_main.layout().setContentsMargins(0, 0, 0, 0)
    widget_scanner = QtWidgets.QWidget()
    widget_main.layout().addWidget(settings_tree)
    widget_main.layout().addWidget(widget_scanner)
    scanner_manager = ScannerManager(widget_scanner, actuators=[])
    
    def update_selection(param): 
        settings.child('actuators').sigValueChanged.disconnect(update_actuators)               
        if param.value():
            d = dict(all_items=settings.child('actuators').value()['all_items'], selected=param.value())
            settings.child('actuators').setValue(d)
        settings.child('actuators').sigValueChanged.connect(update_actuators)
    
    scanner_manager.settings.child('scan_parameters','ordering').sigValueChanged.connect(update_selection)

    def update_actuators(param):
        scanner_manager.actuators = [utils.find_objects_in_list_from_attr_name_val(actuators, 'title', act_str,
                                                                           return_first=True)[0]
                             for act_str in param.value()['selected']]

    def print_info():
        print('info:')
        print(scanner_manager.get_scan_info())
        print('positions:')
        print(scanner_manager.positions)
        print('nav:')
        print(scanner_manager.get_nav_axes())

    settings.child('actuators').sigValueChanged.connect(update_actuators)
    settings.child('set_scan').sigActivated.connect(scanner_manager.set_scan)
    

    # scanner_manager.scanner_updated_signal.connect(print_info)
    widget_main.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    import sys
    from qtpy import QtWidgets
    main()

