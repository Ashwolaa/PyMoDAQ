import re
from typing import List, Tuple


data_name_regexp = re.compile(r"({.*?})+")  # first occurrences of things between {}


def split_formulae(formulae: str) -> List[str]:
    """ Split a string into a list of string for each new line

    Parameters
    ----------
    formulae: str
        The formulae containing various mathematical formula separated with a new line character

    Returns
    -------
    The various formula as a list of string
    """
    return re.split(r'\n', formulae)


def extract_data_names(formula: str) -> List[str]:
    """ Extract the names of the data appearing between curly brackets with a given string formula

    Parameters
    ----------
    formula: str
        The mathematical expression to compute containing in curly brackets the data full names

    Returns
    -------

    """
    data_names = [data_name_with_curly[1:-1] for
                  data_name_with_curly in data_name_regexp.findall(formula)]
    return data_names


def replace_names_in_formula(formula: str):
    formula_tmp = formula[:]
    names = []
    while True:
        m = data_name_regexp.search(formula_tmp)
        if m is not None:
            names.append(m.group())
            formula_tmp = (
                formula_tmp.replace(formula_tmp[m.start(): m.end()],
                                    f'dte.get_data_from_full_name("{m.group()[1:-1]}")'))
        else:
            break
    return formula_tmp, names


def replace_names_in_formula_xr(formula: str, ctx_var: str = '_xr') -> Tuple[str, List[str]]:
    """Like replace_names_in_formula but maps {name} → ctx_var["name"].

    Use when the eval context provides an xarray dict instead of a DataToExport.
    ``{some/path}`` becomes ``_xr["some/path"]`` which resolves to the
    ``xr.Dataset`` stored under that key.
    """
    formula_tmp = formula[:]
    names = []
    while True:
        m = data_name_regexp.search(formula_tmp)
        if m is not None:
            names.append(m.group())
            key = m.group()[1:-1]  # strip { and }
            formula_tmp = formula_tmp.replace(
                formula_tmp[m.start(): m.end()],
                f'{ctx_var}["{key}"]',
            )
        else:
            break
    return formula_tmp, names


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

