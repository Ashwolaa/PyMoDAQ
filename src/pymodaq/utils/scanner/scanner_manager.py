from __future__ import annotations
from typing import Tuple, List, TYPE_CHECKING
from collections import OrderedDict


from qtpy import QtWidgets, QtCore
from qtpy.QtCore import QObject, Signal, Slot

<<<<<<< HEAD
from pymodaq.utils.QObjects.list import SignalList
=======
>>>>>>> 50c3d657 (new scanner manager)
from pymodaq.utils.logger import set_logger, get_module_name
from pymodaq.utils.config import Config
from pymodaq.utils.array_manipulation import makeSnake
from pymodaq.utils.scanner import scanner2
from pymodaq.utils.scanner.scan_factory import ScannerFactory, ScannerBase
from pymodaq.utils.managers.parameter_manager import ParameterManager, Parameter
import pymodaq.utils.daq_utils as utils
import pymodaq.utils.parameter.utils as putils
from pymodaq.utils.scanner.utils import ScanInfo
from pymodaq.utils.plotting.scan_selector import Selector
from pymodaq.utils.data import DataToExport, DataActuator
<<<<<<< HEAD
from itertools import permutations,product
from pymodaq.utils.data import Axis, DataDistribution

=======
from itertools import permutations
>>>>>>> 50c3d657 (new scanner manager)
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
<<<<<<< HEAD
            {'title': 'Scan dimension:', 'name': 'scan_dim', 'type': 'str',
         'readonly':True,},       
            {'title': 'Scan creation:', 'name': 'scan_type', 'type': 'list',
         'limits': ['sequential','global'],'tip':'Sequential: Actuator''s position are set up one at a time;\n Global: Actuator''s positions are set up all at a time'},               
=======
>>>>>>> 50c3d657 (new scanner manager)
            {'title': 'Ordering:', 'name': 'ordering', 'type': 'list',
         'limits': [],},
            {'title': 'Shuffling:', 'name': 'shuffling', 'type': 'list',
         'limits': ['Normal','Snake','Spiral'],'tooltip': 'Defines how the scan goes:'},
        {'title': 'N steps:', 'name': 'n_steps', 'type': 'int', 'value': 0, 'readonly': True},          
         ]},
        {'title': 'Show positions', 'name': 'show_positions', 'type': 'action'},
        
    ]
<<<<<<< HEAD
    limTableSize = 500 #Threshold for displaying in table
=======
>>>>>>> 50c3d657 (new scanner manager)

    def __init__(self, parent_widget: QtWidgets.QWidget = None, scanner_items=OrderedDict([]),
                 actuators: List[DAQ_Move] = [], ordering: Tuple = ()):
        QObject.__init__(self)
        ParameterManager.__init__(self)
        if parent_widget is None:
            parent_widget = QtWidgets.QWidget()
        self.parent_widget = parent_widget
        self._scanners_settings_widget = None
          
<<<<<<< HEAD
        self._scanners = SignalList()
        self._scanners.resized.connect(self._update_steps)

        self._actuators = SignalList()
        self._actuators.resized.connect(self._update_steps)
        self.actuators = actuators
        self.setup_ui()

        self.settings.child('show_positions').sigActivated.connect(self.updateTable)

=======
        self._scanner: ScannerBase = None
        self._scanners = []
        
        self.setup_ui()
        self._actuators = []
        self.actuators = actuators
        
        self.settings.child('show_positions').sigActivated.connect(self.displayPositions)
>>>>>>> 50c3d657 (new scanner manager)

        # for actuator in actuators:
        # self.settings.child('n_steps').setValue(self._scanner.evaluate_steps())

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
<<<<<<< HEAD
        self.makeTable()

    def updateParamTree(self,):
        lim = []
        for perm in list(permutations(range(0,len(self.actuators)))): 
            lim.append(list(self.actuators[ind].title for ind in perm))     
        self.settings.child('scan_parameters','ordering').setLimits(lim)        
        self.settings.child('scan_parameters','scan_dim').setValue(f'{len(self.scanners)}D')   
=======



    def set_scanner(self):

        self._scanners = []
        
        try:
            for actuator in self.actuators:
                scanner: ScannerBase = scanner_factory.get('Scan1D','Linear',actuators=[actuator])
                self._scanners.append(scanner)                                                             
                # self._scanner: ScannerBase = scanner_factory.get(self.settings['scan_type'],
                #                                                 self.settings['scan_sub_type'], actuators=self.actuators)                                                                
                # while True:
                    # child = self._scanner_settings_widget.layout().takeAt(0)
                    # if not child:
                    #     break
                    # child.widget().deleteLater()
                    # QtWidgets.QApplication.processEvents()

                self._scanners_settings_widget.layout().addWidget(scanner.settings_tree)
                scanner.settings.sigTreeStateChanged.connect(self._update_steps)
        except Exception as e:
            print(e)
            pass

>>>>>>> 50c3d657 (new scanner manager)


    def makeSnake2D(self,arr,L1,L2):
        for i in range(L1//2): 
            start = (2*i+1)*L2 
            end = start+L2-1
            arr[[start,end]] = arr[[end,start]]
        return arr

    def value_changed(self, param: Parameter):        
        if param.name() == 'ordering':
            self.updateOrdering()
        elif param.name() == 'show_positions':
            self.displayPositions()           

<<<<<<< HEAD
    def get_indexing(self,shuffler=None):
        indexing = [np.arange(scan.n_steps) for scan in self._scanners]
        indexing_array = np.array(list(product(*indexing)))                      
        return indexing_array
    def get_positions(self,shuffler=None):
        positions = [scan.positions for scan in self._scanners]
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
            self.displayTable.setRowCount(L_steps)                
        else:
            self.displayTable.setRowCount(self.limTableSize)                
        self.displayTable.setColumnCount(1+len(self.scanners))   
        self.displayTable.setHorizontalHeaderLabels(['Steps']+[f'{act.title}' for act in self.actuators])
        for ind,positions in enumerate(positions_array[:self.limTableSize]):
            step_item = QtWidgets.QTableWidgetItem(str(ind))
            step_item.setFlags(step_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.displayTable.setItem(ind,0,step_item)           
            for ind_pos,pos in enumerate(positions):
                pos_item = QtWidgets.QTableWidgetItem(str(pos))
                pos_item.setFlags(pos_item.flags() & ~QtCore.Qt.ItemIsEditable)            
                self.displayTable.setItem(ind,ind_pos+1,pos_item)                 
        self.displayTable.show()
        self.displayTable.resizeColumnsToContents()               


=======

    def get_positions(self,):
        positions = []
        indexing = []
        L_scanner = len(self._scanners)
        for scan in self._scanners:
            pos = np.squeeze(scan.scanner.positions)
            positions.append(pos)        
            indexing.append(np.arange(len(pos))) 
                        
        L_steps = len(all_comb)
            
        
    def displayPositions(self,):
        positions = []
        indexing = []
        L_scanner = len(self._scanners)
        for scan in self._scanners:
            pos = np.squeeze(scan.scanner.positions)
            positions.append(pos)        
            indexing.append(np.arange(len(pos)))
            
        L_index = [len(index) for index in indexing]
            
        import itertools
        from itertools import product       
        all_comb = np.array(list(itertools.product(*positions)))      
             
        # all_indexing = np.array(list(itertools.product(*indexing)))  
        # makeSnake(all_indexing,L_index)                                
        # all_indexing = np.reshape(all_indexing,[L_index[0],L_index[1]*L_index[2],3])
        # for i,index in enumerate(all_indexing):
        #     if i%2:
        #         all_indexing[i] = np.flipud(all_indexing[i])            
        #     all_indexing[i] = makeSnake2D(self,all_indexing[i],L_index[1],L_index[2])        
        # # [0,1;0,2;0,3;1,1;1,2;1,3;2,1;2,2;2,3] ==) [0,1;0,2;0,3;1,3;1,2;1,1;2,1;2,2;2,3]

                        

        # all_indexing[len(indexing[1]):]
        L_steps = len(all_comb)
        # print(all_comb)
        if L_steps<1e3:                
            self.displayTable = QtWidgets.QTableWidget()
            self.displayTable.setColumnCount(1+L_scanner)
            self.displayTable.setRowCount(len(all_comb))                
            self.displayTable.setHorizontalHeaderLabels(['Steps']+[f'{act.title}' for act in self.actuators])
            self.displayTable.verticalHeader().hide()
            for ind,positions in enumerate(all_comb):
                step_item = QtWidgets.QTableWidgetItem(str(ind))
                step_item.setFlags(step_item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.displayTable.setItem(ind,0,step_item)            
                for ind_pos,pos in enumerate(positions):
                    pos_item = QtWidgets.QTableWidgetItem(str(pos))
                    pos_item.setFlags(pos_item.flags() & ~QtCore.Qt.ItemIsEditable)            
                    self.displayTable.setItem(ind,ind_pos+1,pos_item)           
                
            self.displayTable.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
            self.displayTable.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.displayTable.resizeColumnsToContents()
            # self.displayTable.setMaximumWidth(self.displayTable.horizontalHeader().length() + 
            #                  self.displayTable.verticalHeader().width())           
            self.displayTable.show()
        else:
            print('Table is too big, aborting...')
>>>>>>> 50c3d657 (new scanner manager)
    def updateOrdering(self,):                
        if self.settings.child('scan_parameters','ordering').value():
            l1 = self.settings.child('scan_parameters','ordering').value()
            l2 = [act.title for act in self.actuators]
            child = []            
<<<<<<< HEAD
            ordering = np.array([l2.index(item) for item in l1])              
            if ordering is not np.arange(len(self.actuators)):
                for ind in range(len(ordering)):
                    child.append(self._scanners_settings_widget.layout().takeAt(0))            
                for ind in range(len(ordering)):
                    self._scanners_settings_widget.layout().addWidget(child[ordering[ind]].widget())              
                self.actuators = [self.actuators[order] for order in ordering]
                self.scanners = SignalList([self.scanners[order] for order in ordering])

    def makeScanner(self,act):
        scanner = scanner2.ScannerSelector(self._scanners_settings_widget,actuator=act)
        scanner.updateScanner()                
        scanner.scanner.settings.sigTreeStateChanged.connect(self._update_steps)    
=======
            ordering = [l2.index(item) for item in l1]              
            for ind in range(len(ordering)):
                child.append(self._scanners_settings_widget.layout().takeAt(0))            
            for ind in range(len(ordering)):
                self._scanners_settings_widget.layout().addWidget(child[ordering[ind]].widget())              
            self._actuators = [self.actuators[order] for order in ordering]

    def makeScanner(self,act):
        scanner = scanner2.ScannerContainer(self._scanners_settings_widget,actuator=act)
        scanner.updateScanner()        
        scanner.scanner.settings.sigTreeStateChanged.connect(self._update_steps)      
>>>>>>> 50c3d657 (new scanner manager)
        self.scanners.append(scanner)

    def removeScanner(self,act):
        for scan in self.scanners:
            if act == scan.actuator:
                self.scanners.remove(scan)
                ind = self._scanners_settings_widget.layout().indexOf(scan.scanner_settings_widget)
                child = self._scanners_settings_widget.layout().takeAt(ind)
                child.widget().deleteLater()
                QtWidgets.QApplication.processEvents()
<<<<<<< HEAD
=======

>>>>>>> 50c3d657 (new scanner manager)
                
    @property
    def scanner(self,index):
        return self._scanners[index].scanner
<<<<<<< HEAD

=======
>>>>>>> 50c3d657 (new scanner manager)
    @property
    def scanners(self):
        """list of str: Returns as a list the selected scanners that will make the actual scan"""
        return self._scanners
<<<<<<< HEAD
    
    @scanners.setter
    def scanners(self, scan_list):
        """list of str: Returns as a list the selected scanners that will make the actual scan"""
        self._scanners=scan_list
        self._scanners.resized.connect(self._update_steps)
=======
>>>>>>> 50c3d657 (new scanner manager)

    @property
    def actuators(self):
        """list of str: Returns as a list the name of the selected actuators to describe the actual scan"""
        return self._actuators

    @actuators.setter
    def actuators(self, act_list):
<<<<<<< HEAD
=======
        l = [act.title for act in act_list]
>>>>>>> 50c3d657 (new scanner manager)
        for act in act_list:
            if act not in self.actuators:
                self.actuators.append(act)
                self.makeScanner(act)  
        for act in self.actuators:
            if act not in act_list:
                self.actuators.remove(act)
<<<<<<< HEAD
                self.removeScanner(act)          
        self.updateParamTree()

=======
                self.removeScanner(act)  
        lim = []
        for perm in list(permutations(range(0,len(self.actuators)))): 
            lim.append(list(self.actuators[ind].title for ind in perm))     
        self.settings.child('scan_parameters','ordering').setLimits(lim)        

    def set_scan_type_and_subtypes(self, scan_type: str, scan_subtype: str):
        """Convenience function to set the main scan type

        Parameters
        ----------
        scan_type: str
            one of registered Scanner main identifier
        scan_subtype: list of str or None
            one of registered Scanner second identifier for a given main identifier

        See Also
        --------
        ScannerFactory
        """
        if scan_type in scanner_factory.scan_types():
            self.settings.child('scan_type').setValue(scan_type)

            if scan_subtype is not None:
                if scan_subtype in scanner_factory.scan_sub_types(scan_type):
                    self.settings.child('scan_sub_type').setValue(scan_subtype)

    def set_scan_from_settings(self, settings: Parameter, scanner_settings: Parameter):

        self.set_scan_type_and_subtypes(settings['scan_type'],
                                        settings['scan_sub_type'])
        self.settings.restoreState(settings.saveState())
        self._scanner.settings.restoreState(scanner_settings.saveState())

    @property
    def scan_type(self) -> str:
        return self.settings['scan_type']

    @property
    def scan_sub_type(self) -> str:
        return self.settings['scan_sub_type']

    # def connect_things(self):
    #     self.settings.child('calculate_positions').sigActivated.connect(self.set_scan)
>>>>>>> 50c3d657 (new scanner manager)

    def get_scan_info(self) -> ScanInfo:
        """Get a summary of the configured scan as a ScanInfo object"""
        return ScanInfo(self._scanner.n_steps, positions=self._scanner.positions,
                        axes_indexes=self._scanner.axes_indexes, axes_unique=self._scanner.axes_unique,
                        selected_actuators=[act.title for act in self.actuators])

<<<<<<< HEAD
    def get_nav_axes(self) -> List[Axis]:
        return [scan.get_nav_axes()[0] for scan in self.scanners]     


    def get_scan_shape(self):
        return tuple([len(scan.axes_unique) for scan in self.scanners])
=======
    def get_nav_axes(self):
        return self._scanner.get_nav_axes()

    def get_scan_shape(self):
        return self._scanner.get_scan_shape()
>>>>>>> 50c3d657 (new scanner manager)

    def get_indexes_from_scan_index(self, scan_index: int) -> Tuple[int]:
        """To be reimplemented. Calculations of indexes within the scan"""
        return self._scanner.get_indexes_from_scan_index(scan_index)

    def _update_steps(self):
<<<<<<< HEAD
        self.settings.child('scan_parameters','n_steps').setValue(self.tot_steps)                     

    @property
    def steps(self):
        return [scan.n_steps for scan in self.scanners]     

    @property
    def tot_steps(self):
        return np.prod(self.steps)
=======
        self.settings.child('scan_parameters','n_steps').setValue(self.n_steps)                     

    @property
    def n_steps(self):
        steps = 1 
        for scan in self.scanners:
            steps *= scan.scanner.evaluate_steps()
        return steps
>>>>>>> 50c3d657 (new scanner manager)

    @property
    def n_axes(self):        
        return len(self.scanners)

    @property
    def positions(self):
<<<<<<< HEAD
        return self.get_positions()
      
=======
        return self._scanner.positions
    
    @property
    def positions(self,scan='all'):        
        self._scanners.index(scan)
        return self._scanner.positions    

>>>>>>> 50c3d657 (new scanner manager)
    def positions_at(self, index: int) -> DataToExport:
        """ Extract the actuators positions at a given index in the scan as a DataToExport of DataActuators"""
        dte = DataToExport('scanner')
        for ind, pos in enumerate(self.positions[index]):
            dte.append(DataActuator(self.actuators[ind].title, data=float(pos)))
        return dte

    @property
    def axes_indexes(self):
        return self._scanner.axes_indexes
<<<<<<< HEAD
    
    @property
    def axes_unique(self):
        return [scan.axes_unique for scan in self.scanners]     
=======

    @property
    def axes_unique(self):
        return self._scanner.axes_unique
>>>>>>> 50c3d657 (new scanner manager)

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
    

    scanner_manager.scanner_updated_signal.connect(print_info)
    widget_main.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    import sys
    from qtpy import QtWidgets
    main()

