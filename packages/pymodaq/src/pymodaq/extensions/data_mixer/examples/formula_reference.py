"""Formula syntax reference for DataMixerModelH5.

Demonstrates every formula feature supported by ``parse_named_formulae``
and ``replace_names_in_formula``.  Run this script to see the parsed
output for each example without needing any H5 file or Qt.
"""
import textwrap

from pymodaq.extensions.data_mixer.parser import (
    parse_named_formulae,
    extract_formula_output_names,
    replace_names_in_formula,
)


def show(label: str, formula_text: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")
    raw = textwrap.indent(formula_text.strip(), '    | ')
    print(raw)

    parsed = parse_named_formulae(formula_text)
    names  = extract_formula_output_names(formula_text)

    print(f"\n  parse_named_formulae → {len(parsed)} formula(s):")
    for output_name, expr in parsed:
        expanded, _ = replace_names_in_formula(expr)
        print(f"    [{output_name!r}]  expr    = {expr!r}")
        print(f"             expanded = {expanded!r}")

    if names:
        print(f"\n  autocomplete names → {names}")


# ── 1. Named output ──────────────────────────────────────────────────────────
show(
    "Named output — result = expr",
    """
result = {Scan000/Data1D/channel00} * 2
"""
)

# ── 2. Bare expression (auto-named) ─────────────────────────────────────────
show(
    "Bare expression — auto-named Formula_NNN",
    """
{Scan000/Data1D/channel00} + 1
"""
)

# ── 3. Comments and blank lines ──────────────────────────────────────────────
show(
    "Comments (#) and blank lines are ignored",
    """
# This line is a comment and will be skipped

corrected = {signal} - {background}

# Another comment
normalised = {corrected} / np.max(np.abs({corrected}))
"""
)

# ── 4. Cross-referencing (sequential formulas) ───────────────────────────────
show(
    "Cross-referencing — later formulas can use earlier results via {name}",
    """
a = {raw_signal} * 2
b = {a} + {offset}
c = np.sqrt(np.abs({b}))
"""
)

# ── 5. NumPy constants in expressions ────────────────────────────────────────
show(
    "NumPy constants are available as 'np.*'",
    """
pi_scaled = {signal} * np.pi
two_pi    = {signal} * (2 * np.pi)
"""
)

# Note: numpy *reduction functions* (np.convolve, np.gradient, np.max …) do
# NOT work directly on DataWithAxes.  Use arithmetic operators instead, or
# extract the raw array via {key}.data[0] when you need a reduction (the
# result will then be a plain ndarray, not a DataWithAxes).

# ── 6. Multi-operand expressions ─────────────────────────────────────────────
show(
    "Multiple data references in one expression",
    """
sum_channels = {ch0} + {ch1} + {ch2}
ratio        = {numerator} / ({denominator} + 1e-9)
"""
)

# ── 7. Invalid LHS (not a Python identifier) ─────────────────────────────────
show(
    "Invalid LHS — falls back to auto-name",
    """
1st_result = {signal}
result-dash = {signal}
valid_result = {signal}
"""
)

print("\n" + "═" * 60)
print("  Formula syntax summary")
print("═" * 60)
print("""
  {key}             — reference any H5 data key or earlier result
  name = expr       — name the output (must be a valid Python identifier)
  expr              — unnamed line, auto-named Formula_NNN
  # comment         — ignored entirely
  (blank line)      — ignored entirely

  Available in eval scope:
    np              — numpy (constants like np.pi work; reduction functions
                      like np.convolve / np.gradient do NOT work on
                      DataWithAxes — use arithmetic operators instead)
    dte             — DataToExport containing all H5 data + earlier results
""")
