# Plan: H5-Based Data Mixer Model with Pattern Autocomplete

## Context

The DataMixer extension currently processes data from live detector grabs via `det_done_signal`. The goal is a new model that operates **directly on an H5 file** — enabling both live scan processing (reading the scan H5 that is actively being written) and offline analysis of any saved H5 file.

Formulas use the `text_pattern` parameter type for `{`-triggered autocomplete of H5 data keys. Named formula outputs (`result = {key} + 2`) appear in the autocomplete list in real-time as you type. The new SWMR utilities on this branch enable the reader to see the latest data in a live H5 file without any signal coupling to DAQScan.

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `packages/pymodaq/src/pymodaq/extensions/data_mixer/models/h5_model.py` | **CREATE** |
| `packages/pymodaq/src/pymodaq/extensions/data_mixer/parser.py` | **MODIFY** — add named formula parsing |
| `packages/pymodaq/src/pymodaq/extensions/scan/daq_scan.py` | **NOT modified** |

**Model auto-discovery:** placing `h5_model.py` in the `models/` folder is sufficient — `get_models()` in `model.py` scans this folder automatically (via `pkgutil.iter_modules`). The class must inherit **directly** from `DataMixerModel` due to the `klass.__base__ is DataMixerModel` check at `model.py:95`.

---

## Part 1: Parser update

**File:** `packages/pymodaq/src/pymodaq/extensions/data_mixer/parser.py`

Add two functions. The existing `split_formulae`, `extract_data_names`, `replace_names_in_formula` remain unchanged.

```python
def parse_named_formulae(formulae: str) -> List[Tuple[str, str]]:
    """Parse 'name = expression' or bare 'expression' lines.

    Returns list of (output_name, expression) tuples.
    Lines starting with '#' and blank lines are skipped.
    Lines without '=' or whose left side is not a valid identifier
    get an auto-name like 'Formula_000'.
    """
    result = []
    for i, line in enumerate(re.split(r'\n', formulae)):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            name, expr = line.split('=', 1)
            name = name.strip()
            if name.isidentifier():
                result.append((name, expr.strip()))
                continue
        result.append((f'Formula_{i:03d}', line))
    return result


def extract_formula_output_names(formulae: str) -> List[str]:
    """Return all identifiers defined on the left-hand side of '=' in formulae text.

    Used for real-time autocomplete: as soon as the user writes 'myvar = ...',
    'myvar' becomes available in the '{' autocomplete for subsequent lines.
    """
    names = []
    for line in re.split(r'\n', formulae):
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            name = line.split('=', 1)[0].strip()
            if name.isidentifier():
                names.append(name)
    return names
```

---

## Part 2: New model `DataMixerModelH5`

**File:** `packages/pymodaq/src/pymodaq/extensions/data_mixer/models/h5_model.py`

### Imports

```python
from pathlib import Path
from typing import List, Optional

import numpy as np  # must be importable in eval() scope

from pymodaq.extensions.data_mixer.model import DataMixerModel
from pymodaq.extensions.data_mixer.parser import (
    parse_named_formulae, extract_formula_output_names,
    replace_names_in_formula)

from pymodaq_data.h5modules.data_saving import DataLoader, H5SaverLowLevel
from pymodaq_data.h5modules.swmr import refresh_datasets
from pymodaq_data.h5modules import is_file_swmr_active
from pymodaq_data.data import DataToExport

from qtpy.QtCore import QTimer
from pymodaq_utils.logger import set_logger, get_module_name

logger = set_logger(get_module_name(__file__))
```

### Params

```python
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
```

### `ini_model()`

```python
    def ini_model(self):
        self._h5saver_low: Optional[H5SaverLowLevel] = None
        self._h5_data_names: List[str] = []
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._timer_refresh)
        self._connect_formula_text_changed()
```

`_connect_formula_text_changed` hooks into the `text_pattern` widget's `textChanged` signal for real-time autocomplete:

```python
    def _connect_formula_text_changed(self):
        param = self.settings.child('edit_formula')
        # param.items is a list of PatternParameterItem instances
        items = getattr(param, 'items', [])
        if items and hasattr(items[0], 'widget') and items[0].widget is not None:
            items[0].widget.textChanged.connect(self.on_formula_text_changed)
```

### `update_settings(param)`

```python
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
```

### Live mode helpers

```python
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
        # Auto-update path if scan restarted
        if self.settings['live_scan']:
            live_path = self._get_live_h5_path()
            if live_path is not None:
                current = Path(self.settings['h5_file'])
                if live_path != current:
                    self._open_h5(live_path)
                    self.settings.child('h5_file').setValue(str(live_path))

        if self._h5saver_low is not None and self._h5saver_low.isopen():
            try:
                refresh_datasets(self._h5saver_low.root())
            except Exception:
                pass
        self.compute()
```

### H5 file management

```python
    def load_h5_keys(self):
        h5_path = Path(self.settings['h5_file'])
        if not h5_path.is_file():
            return
        self._open_h5(h5_path)
        self._refresh_h5_data_names()
        self._update_completions()

    def _open_h5(self, path: Path):
        self._close_h5()
        swmr = is_file_swmr_active(path)
        self._h5saver_low = H5SaverLowLevel()
        self._h5saver_low.open_file(str(path), mode='r', swmr_mode=swmr)

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
```

### Autocomplete

```python
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
```

### Core formula evaluation

```python
    def compute(self):
        if self._h5saver_low is None or not self._h5saver_low.isopen():
            return
        try:
            loader = DataLoader(self._h5saver_low)
            dte_from_h5 = loader.load_all('/')

            formulae = parse_named_formulae(self.settings['edit_formula'])
            dte_processed = DataToExport('Computed')
            # dte_combined grows as each formula result is appended,
            # enabling later formulas to reference earlier results via {name}
            dte_combined = DataToExport('Combined')
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
        """Evaluate one formula line. np and dte are available in the eval scope."""
        formula_to_eval, _ = replace_names_in_formula(formula)
        dwa = eval(formula_to_eval)   # np and dte are in local scope
        dwa.name = name
        return dwa

    def process_dte(self, measurements: DataToExport) -> DataToExport:
        """Base class contract. H5 model ignores detector-based measurements."""
        self.compute()
        return DataToExport('Computed')
```

---

## Data Flow

### Offline H5

```
User selects H5 file path  (h5_file browsepath param)
  → load_h5_keys()
      _open_h5(path)          ← opens file, SWMR auto-detected
      _refresh_h5_data_names() ← loader.load_all() → dte.get_full_names()
      _update_completions()   ← sets '{' completions = h5_names + formula_names
  ↓
User writes formulas in text_pattern widget:
  "a = {Scan000/Data0D/channel_00}"
  "b = {a} * 2"
  ↓
  on_formula_text_changed() fires on each keystroke:
    extract_formula_output_names() → ['a', 'b']
    update_completions('{', h5_names + ['a', 'b'])
    → '{a}' is now in the autocomplete dropdown
  ↓
User clicks Compute
  → compute()
      loader.load_all() → dte_from_h5
      parse_named_formulae() → [('a', '{...}'), ('b', '{a} * 2')]
      eval 'a' → dwa_a; dte_combined.append(dwa_a)
      eval 'b' → uses {a} = dwa_a; dte_combined.append(dwa_b)
      dte_computed_signal.emit(dte_processed)
      → ViewerDispatcher plots result
```

### Live Scan (SWMR)

```
User enables "Use Live Scan H5"
  → _start_live_mode()
      _get_live_h5_path()  ← dashboard.extensions['DAQScan'].h5saver.h5_file_path
      _open_h5(path, swmr=True)   ← H5SaverLowLevel in SWMR reader mode
      QTimer.start(1000 ms)
  ↓
Every 1000 ms (QTimer fires):
  _timer_refresh()
    refresh_datasets(root)    ← h5py SWMR: see latest written data
    compute()
      loader.load_all()       ← reads current state of file
      evaluate formulas       ← results include navigation axes from H5
      dte_computed_signal     ← viewer updates with accumulated scan data
```

---

## Key Reused Infrastructure

| Component | Location | Role |
|-----------|----------|------|
| `DataLoader` | `pymodaq_data/h5modules/data_saving.py:1044` | Load H5 → `DataToExport` |
| `H5SaverLowLevel.open_file(mode='r', swmr_mode=)` | `pymodaq_data/h5modules/saving.py` | SWMR-aware reader |
| `refresh_datasets` | `pymodaq_data/h5modules/swmr.py:62` | Refresh SWMR reader |
| `is_file_swmr_active` | `pymodaq_data/h5modules/__init__.py:97` | Auto-detect SWMR |
| `replace_names_in_formula` | `data_mixer/parser.py:40` | `{key}` → `dte.get_data_from_full_name(key)` |
| `PatternParameter.update_completions` | `pymodaq_gui/.../text_pattern.py:141` | Update `{` dropdown |
| `DataMixer.dte_computed_signal` | `data_mixer/data_mixer.py:47` | Emit to ViewerDispatcher |

---

## Verification Checklist

1. **Offline file**: Select a `.h5` scan file → Load Keys → `{` autocomplete shows H5 dataset names → `result = {Scan000/Data0D/ch00} * 2` → Compute → result visible in viewer
2. **Cross-referencing**: Line 1: `a = {scan/data}` | Line 2: `b = {a} + 1` → both compute correctly in order
3. **Real-time autocomplete**: After typing `a = ...` on line 1, typing `{` on line 2 shows `a` in the dropdown immediately
4. **Live scan (SWMR enabled)**: Open DataMixer → enable "Use Live Scan H5" → start a DAQScan → computed viewer updates at each refresh interval with navigation axes inherited from the H5 file
5. **Live scan (no SWMR)**: Same as above but fallback to normal read mode (opens/reads without SWMR flags)
6. **No scan running**: "Use Live Scan H5" with no active scan → gracefully does nothing, user can manually set H5 path
