"""Offline H5 analysis with DataMixerModelH5 — no GUI required.

This script shows the core workflow:
  1. Create a synthetic H5 scan file (stands in for a real DAQScan output).
  2. Open it with the model's H5 helpers.
  3. List the available data keys.
  4. Evaluate named formulas against those keys.
  5. Inspect the results.

Run directly:
    python h5_model_offline.py
"""
from pathlib import Path
import tempfile

import numpy as np

from pymodaq_data.data import DataToExport, DataWithAxes, DataSource
from pymodaq_data.h5modules.saving import H5SaverLowLevel
from pymodaq_data.h5modules.data_saving import DataSaverLoader, DataLoader

from pymodaq.extensions.data_mixer.parser import (
    parse_named_formulae,
    extract_formula_output_names,
    replace_names_in_formula,
)


# ── 1. Build a synthetic H5 file ────────────────────────────────────────────

def create_demo_h5(file_path: Path) -> None:
    """Write a noisy sine wave into an H5 file (one dataset)."""
    x = np.linspace(0, 2 * np.pi, 200)
    rng = np.random.default_rng(0)
    noisy_signal = np.sin(x) + rng.normal(0, 0.05, size=x.size)

    dwa = DataWithAxes('signal', source=DataSource['raw'], data=[noisy_signal])

    writer = H5SaverLowLevel()
    writer.init_file(file_name=file_path, new_file=True)
    DataSaverLoader(writer).add_data('/RawData', dwa)
    writer.close_file()
    print(f"H5 file written to: {file_path}")


# ── 2. Load available keys ───────────────────────────────────────────────────

def load_keys(file_path: Path):
    """Return the list of full data names found in the H5 file."""
    reader = H5SaverLowLevel()
    reader.open_file(str(file_path), mode='r')
    loader = DataLoader(reader)
    dte = loader.load_all('/')
    reader.close_file()
    return dte.get_full_names(), dte


# ── 3. Evaluate named formulas ───────────────────────────────────────────────

def compute_formulas(formula_text: str, dte_from_h5: DataToExport) -> DataToExport:
    """Parse and evaluate each formula line; later lines can reference earlier results.

    Parameters
    ----------
    formula_text:
        Multi-line string; each non-blank, non-comment line is one formula.
        Lines of the form  ``name = expression``  name the output.
        Lines without a valid LHS identifier get an auto-name ``Formula_NNN``.
    dte_from_h5:
        DataToExport loaded from the H5 file.

    Returns
    -------
    DataToExport with one DataWithAxes per formula line.
    """
    formulae = parse_named_formulae(formula_text)
    dte_processed = DataToExport('Computed')
    # 'dte' is the name eval() looks up — it grows as each result is appended
    dte = DataToExport('Combined')
    for dwa in dte_from_h5.data:
        dte.append(dwa)

    for name, formula in formulae:
        formula_to_eval, _ = replace_names_in_formula(formula)
        try:
            dwa = eval(formula_to_eval)  # np and dte are in local scope
            dwa.name = name
            dte_processed.append(dwa)
            dte.append(dwa)
            print(f"  {name!r:20s}  shape={dwa.data[0].shape}  "
                  f"min={dwa.data[0].min():.4f}  max={dwa.data[0].max():.4f}")
        except Exception as exc:
            print(f"  ERROR in formula {name!r}: {exc}")

    return dte_processed


# ── 4. Main ──────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as tmp:
        h5_path = Path(tmp) / 'demo_scan.h5'
        create_demo_h5(h5_path)

        print("\nAvailable data keys:")
        keys, dte = load_keys(h5_path)
        for k in keys:
            print(f"  {k}")

        # ---- formula text the user would type in the GUI ----
        # Use the first available key; adjust to match your own H5 file.
        raw_key = keys[0]

        # DataWithAxes supports arithmetic operators (+, -, *, /).
        # NumPy reduction functions (np.convolve, np.gradient, np.max …)
        # do not work directly on DataWithAxes — use .data[0] to access
        # the underlying array when you need them.
        formula_text = f"""\
# Invert the raw signal
inverted = {{{raw_key}}} * -1
# Shift up by 1  (cross-references {{inverted}})
shifted = {{inverted}} + 1.0
# Average of raw and shifted — demonstrates two-operand formula
average = ({{{raw_key}}} + {{shifted}}) * 0.5
"""

        print("\nDefined output names (for '{' autocomplete):")
        for name in extract_formula_output_names(formula_text):
            print(f"  {name}")

        print("\nComputing formulas:")
        results = compute_formulas(formula_text, dte)

        print(f"\nDone — {len(results.data)} result(s) computed.")
