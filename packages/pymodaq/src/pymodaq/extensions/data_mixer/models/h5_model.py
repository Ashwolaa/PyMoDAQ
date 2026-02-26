from pathlib import Path
from typing import List, Optional

import numpy as np  # must be importable in eval() scope

from pymodaq.extensions.data_mixer.model import DataMixerModel
from pymodaq.extensions.data_mixer.parser import (
    parse_named_formulae, extract_formula_output_names,
    replace_names_in_formula)

from pymodaq_data.h5modules.data_saving import DataLoader
from pymodaq_data.h5modules.saving import H5SaverLowLevel
from pymodaq_data.h5modules.backends import backends_available
from pymodaq_data.data import DataToExport, DataWithAxes, DataSource


def _wrap_result(result, name: str) -> DataWithAxes:
    """Coerce any eval() return value to a named DataWithAxes.

    Handled types:
      DataWithAxes           — rename in place and return
      np.ndarray             — wrap as single-array DataWithAxes
      tuple/list of ndarray  — np.gradient & similar return one array per axis;
                               each component is stored as a separate array in
                               DataWithAxes.data so {name}.data[0] gives axis-0,
                               {name}.data[1] gives axis-1, etc.
      scalar (int/float/…)   — wrap as 1-element array
    """
    if isinstance(result, DataWithAxes):
        result.name = name
        return result
    if isinstance(result, np.ndarray):
        return DataWithAxes(name, source=DataSource['calculated'], data=[result])
    if isinstance(result, (tuple, list)) and all(isinstance(r, np.ndarray) for r in result):
        return DataWithAxes(name, source=DataSource['calculated'], data=list(result))
    if isinstance(result, (int, float, np.integer, np.floating, np.bool_)):
        return DataWithAxes(name, source=DataSource['calculated'],
                            data=[np.array([float(result)])])
    raise TypeError(
        f'Formula returned {type(result).__name__!r} — expected a DataWithAxes, '
        f'numpy array, tuple of arrays, or scalar.')


class FormulaDTE(DataToExport):
    """DataToExport that also resolves plain names (no origin/name slash).

    The base get_data_from_full_name always splits on '/' and takes index [1],
    which crashes on a bare name like 'a'.  Formula results carry plain names,
    so we add a fallback that matches by .name directly.
    """
    def get_data_from_full_name(self, full_name: str, deepcopy: bool = False):
        if '/' in full_name:
            return super().get_data_from_full_name(full_name, deepcopy)
        matches = [dwa for dwa in self.data if dwa.name == full_name]
        if not matches:
            raise KeyError(f'No data named {full_name!r}')
        dwa = matches[0]
        return dwa.deepcopy() if deepcopy else dwa

from qtpy.QtCore import QTimer
from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))


class DataMixerModelH5(DataMixerModel):

    params = [
        {'title': 'H5 File:', 'name': 'h5_file', 'type': 'browsepath', 'value': ''},
        {'title': 'Load Keys', 'name': 'load_keys', 'type': 'bool_push', 'value': False,
         'label': 'Load Keys'},
        {'title': 'Use Live Scan H5', 'name': 'live_scan', 'type': 'bool', 'value': False,
         'tip': 'Auto-use the H5 file from current DAQScan and refresh periodically'},
        {'title': 'Refresh interval (ms)', 'name': 'refresh_interval', 'type': 'int',
         'value': 1000, 'min': 100},
        {'title': 'Formula editor:', 'name': 'edit_formula', 'type': 'text_pattern',
         'value': '',
         'patterns': {'{': []},
         'completer_config': {'min_width': 300, 'case_sensitive': False}},
        {'title': 'Compute', 'name': 'compute', 'type': 'bool_push', 'value': False,
         'label': 'Compute'},
    ]

    def ini_model(self):
        self._h5saver_low: Optional[H5SaverLowLevel] = None
        self._h5_data_names: List[str] = []
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._timer_refresh)
        self._connect_formula_text_changed()

    def _connect_formula_text_changed(self):
        param = self.settings.child('edit_formula')
        items = getattr(param, 'items', [])
        if items and hasattr(items[0], 'widget') and items[0].widget is not None:
            items[0].widget.textChanged.connect(self.on_formula_text_changed)

    def update_settings(self, param):
        if param.name() == 'load_keys':
            self.load_h5_keys()
        elif param.name() == 'h5_file':
            self.load_h5_keys()
        elif param.name() == 'compute':
            self.compute()
        elif param.name() == 'live_scan':
            if param.value():
                self._start_live_mode()
            else:
                self._stop_live_mode()
        elif param.name() == 'refresh_interval':
            if self._refresh_timer.isActive():
                self._refresh_timer.setInterval(param.value())

    def _start_live_mode(self):
        live_path = self._get_live_h5_path()
        if live_path is not None:
            self.settings.child('h5_file').setValue(str(live_path))
        self.load_h5_keys()
        self._refresh_timer.start(self.settings['refresh_interval'])

    def _stop_live_mode(self):
        self._refresh_timer.stop()

    def _get_live_h5_path(self) -> Optional[Path]:
        """Try to get the currently open scan H5 path from DAQScan extension."""
        try:
            from pymodaq.extensions import ExtensionEnum
            daq_scan = self.data_mixer.dashboard.extensions.get(ExtensionEnum['DAQScan'])
            if daq_scan is not None and daq_scan.h5saver.isopen():
                return daq_scan.h5saver.h5_file_path
        except Exception:
            pass
        return None

    def _timer_refresh(self):
        """Called by QTimer; refresh SWMR reader and recompute."""
        if self.settings['live_scan']:
            live_path = self._get_live_h5_path()
            if live_path is not None:
                current = Path(self.settings['h5_file'])
                if live_path != current:
                    self._open_h5(live_path)
                    self.settings.child('h5_file').setValue(str(live_path))

        self.compute()

    def load_h5_keys(self):
        h5_path = Path(self.settings['h5_file'])
        if not h5_path.is_file():
            return
        self._open_h5(h5_path)
        self._refresh_h5_data_names()
        self._update_completions()

    def _open_h5(self, path: Path):
        self._close_h5()
        # Try each backend in preference order; scan files are almost always
        # written with 'tables', so try that first regardless of env default.
        errors = {}
        for backend in [b for b in ('tables', 'h5py') if b in backends_available]:
            h5saver = H5SaverLowLevel(backend=backend)
            try:
                h5saver.init_file(file_name=path, new_file=False)
                loader = DataLoader(h5saver)
                loader.load_all('/')          # probe: fails fast if wrong backend
                h5saver.close_file()
                # Re-open cleanly for actual use
                h5saver2 = H5SaverLowLevel(backend=backend)
                h5saver2.init_file(file_name=path, new_file=False)
                self._h5saver_low = h5saver2
                return
            except Exception as exc:
                errors[backend] = exc
                try:
                    h5saver.close_file()
                except Exception:
                    pass
        raise RuntimeError(
            f'Could not open {path} with any backend.\n'
            + '\n'.join(f'  {b}: {e}' for b, e in errors.items())
        )

    def _close_h5(self):
        if self._h5saver_low is not None and self._h5saver_low.isopen():
            self._h5saver_low.close_file()
        self._h5saver_low = None

    def _refresh_h5_data_names(self):
        if self._h5saver_low is None:
            return
        try:
            loader = DataLoader(self._h5saver_low)
            dte = loader.load_all('/')
            self._h5_data_names = dte.get_full_names()
        except Exception as e:
            logger.exception(str(e))

    def on_formula_text_changed(self):
        """Real-time: whenever the formula text changes, add defined variable names to '{' completions."""
        formula_text = self.settings['edit_formula']
        formula_names = extract_formula_output_names(formula_text)
        completions = self._h5_data_names + formula_names
        self.settings.child('edit_formula').update_completions('{', completions)

    def _update_completions(self):
        """Called after loading H5 keys to populate the initial completion list."""
        formula_names = extract_formula_output_names(self.settings['edit_formula'])
        completions = self._h5_data_names + formula_names
        self.settings.child('edit_formula').update_completions('{', completions)

    def compute(self):
        if self._h5saver_low is None or not self._h5saver_low.isopen():
            return
        try:
            loader = DataLoader(self._h5saver_low)
            dte_from_h5 = loader.load_all('/')

            formulae = parse_named_formulae(self.settings['edit_formula'])
            dte_processed = DataToExport('Computed')
            dte_combined = FormulaDTE('Combined')
            for dwa in dte_from_h5.data:
                dte_combined.append(dwa)

            for name, formula in formulae:
                try:
                    dwa = self._compute_formula(formula, dte_combined, name)
                    dte_processed.append(dwa)
                    dte_combined.append(dwa)
                except Exception as e:
                    logger.exception(f'Formula "{name}": {e}')

            self.data_mixer.dte_computed_signal.emit(dte_processed)
        except Exception as e:
            logger.exception(str(e))

    def _compute_formula(self, formula: str, dte: DataToExport, name: str):
        """Evaluate one formula line. np and dte are available in the eval scope.

        If the expression returns a plain numpy array (e.g. from np.gradient or
        np.convolve called on {key}.data[0]) it is automatically wrapped in a
        DataWithAxes so downstream code can always treat the result uniformly.
        """
        formula_to_eval, _ = replace_names_in_formula(formula)
        result = eval(formula_to_eval)  # np and dte are in local scope
        return _wrap_result(result, name)

    def process_dte(self, measurements: DataToExport) -> DataToExport:
        """Base class contract. H5 model ignores detector-based measurements."""
        self.compute()
        return DataToExport('Computed')
