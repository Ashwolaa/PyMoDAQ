import pytest

from pymodaq.extensions.data_mixer.parser import (
    parse_named_formulae,
    extract_formula_output_names,
    replace_names_in_formula_xr,
)


class TestParseNamedFormulae:

    def test_empty_string_returns_empty(self):
        assert parse_named_formulae('') == []

    def test_blank_lines_only_returns_empty(self):
        assert parse_named_formulae('\n\n\n') == []

    def test_comment_line_skipped(self):
        assert parse_named_formulae('# this is a comment') == []

    def test_comments_and_blanks_mixed(self):
        assert parse_named_formulae('# comment\n\n# another') == []

    def test_named_formula_simple(self):
        result = parse_named_formulae('result = {key} * 2')
        assert result == [('result', '{key} * 2')]

    def test_named_formula_whitespace_stripped(self):
        result = parse_named_formulae('  result  =  {key} * 2  ')
        assert result == [('result', '{key} * 2')]

    def test_bare_expression_gets_autoname(self):
        result = parse_named_formulae('{key} + 1')
        assert result == [('Formula_000', '{key} + 1')]

    def test_invalid_lhs_not_identifier_gets_autoname(self):
        result = parse_named_formulae('1bad = {key}')
        assert result == [('Formula_000', '1bad = {key}')]

    def test_lhs_with_spaces_is_valid_identifier(self):
        result = parse_named_formulae('my_var = {key}')
        assert result == [('my_var', '{key}')]

    def test_multiline_all_named(self):
        text = 'a = {x}\nb = {y}'
        result = parse_named_formulae(text)
        assert result == [('a', '{x}'), ('b', '{y}')]

    def test_multiline_with_comment_and_blank(self):
        text = '# skip this\n\na = {x}\nb = {y}'
        result = parse_named_formulae(text)
        assert result == [('a', '{x}'), ('b', '{y}')]

    def test_autoname_index_reflects_original_line_number(self):
        # blank at line 0 is skipped; expression at line 1 → Formula_001
        result = parse_named_formulae('\n{key}')
        assert result == [('Formula_001', '{key}')]

    def test_mixed_named_and_bare(self):
        text = 'a = {x}\n{y} + 1\nb = {a}'
        result = parse_named_formulae(text)
        assert result[0] == ('a', '{x}')
        assert result[1][0] == 'Formula_001'   # bare line at index 1
        assert result[2] == ('b', '{a}')

    def test_rhs_with_two_operands(self):
        result = parse_named_formulae('out = {x} + {y}')
        assert result == [('out', '{x} + {y}')]

    def test_trailing_comment_not_confused_with_formula(self):
        # Formula lines starting with '#' are skipped entirely
        text = '# a = {x}\na = {y}'
        result = parse_named_formulae(text)
        assert result == [('a', '{y}')]

    def test_returns_list_of_tuples(self):
        result = parse_named_formulae('a = {x}')
        assert isinstance(result, list)
        assert isinstance(result[0], tuple)
        assert len(result[0]) == 2


class TestExtractFormulaOutputNames:

    def test_empty_string_returns_empty(self):
        assert extract_formula_output_names('') == []

    def test_blank_lines_returns_empty(self):
        assert extract_formula_output_names('\n\n') == []

    def test_single_named_formula(self):
        assert extract_formula_output_names('a = {x}') == ['a']

    def test_multiple_named_formulas(self):
        result = extract_formula_output_names('a = {x}\nb = {y}')
        assert result == ['a', 'b']

    def test_comment_line_excluded(self):
        result = extract_formula_output_names('# a = {x}\nb = {y}')
        assert result == ['b']

    def test_invalid_identifier_excluded(self):
        result = extract_formula_output_names('1bad = {x}')
        assert result == []

    def test_bare_expression_excluded(self):
        result = extract_formula_output_names('{x} + 1')
        assert result == []

    def test_blank_lines_between_named_formulas(self):
        result = extract_formula_output_names('a = {x}\n\nb = {y}')
        assert result == ['a', 'b']

    def test_order_preserved(self):
        result = extract_formula_output_names('c = {z}\na = {x}\nb = {y}')
        assert result == ['c', 'a', 'b']

    def test_underscore_identifier_accepted(self):
        result = extract_formula_output_names('my_result = {data}')
        assert result == ['my_result']

    def test_mixed_valid_and_invalid(self):
        text = 'good = {x}\n1bad = {y}\nalso_good = {z}'
        result = extract_formula_output_names(text)
        assert result == ['good', 'also_good']


class TestReplaceNamesInFormulaXr:

    def test_single_h5_ref_becomes_xr_lookup(self):
        result, names = replace_names_in_formula_xr('{scan/CH00}')
        assert result == '_xr["scan/CH00"]'
        assert names == ['{scan/CH00}']

    def test_computed_ref_auto_dereferences(self):
        result, _ = replace_names_in_formula_xr('{a}', computed_names={'a'})
        assert result == '_xr["a"]["a"]'

    def test_h5_ref_no_computed_names_stays_dataset(self):
        result, _ = replace_names_in_formula_xr('{scan/CH00}', computed_names=set())
        assert result == '_xr["scan/CH00"]'

    def test_computed_names_none_always_produces_dataset(self):
        result, _ = replace_names_in_formula_xr('{a}', computed_names=None)
        assert result == '_xr["a"]'

    def test_multiple_refs_in_one_formula(self):
        result, names = replace_names_in_formula_xr(
            '{x} + {y}', computed_names={'x'})
        assert '_xr["x"]["x"]' in result   # computed → DataArray
        assert '_xr["y"]' in result         # H5 → Dataset
        assert len(names) == 2

    def test_ref_mixed_with_operators(self):
        result, _ = replace_names_in_formula_xr('{a}.mean("t")', computed_names={'a'})
        assert result.startswith('_xr["a"]["a"]')
        assert '.mean("t")' in result

    def test_custom_ctx_var(self):
        result, _ = replace_names_in_formula_xr('{k}', ctx_var='ctx')
        assert result == 'ctx["k"]'

    def test_no_refs_returns_formula_unchanged(self):
        formula = 'np.ones(10) * 2'
        result, names = replace_names_in_formula_xr(formula)
        assert result == formula
        assert names == []

    def test_returns_tuple_of_str_and_list(self):
        result, names = replace_names_in_formula_xr('{k}')
        assert isinstance(result, str)
        assert isinstance(names, list)

    def test_name_in_computed_set_not_present_stays_dataset(self):
        # {other} is NOT in computed_names → should remain Dataset lookup
        result, _ = replace_names_in_formula_xr('{other}', computed_names={'a'})
        assert result == '_xr["other"]'

    def test_path_with_slash_treated_as_h5_key(self):
        result, _ = replace_names_in_formula_xr(
            '{origin/name}', computed_names={'a'})
        assert result == '_xr["origin/name"]'

    def test_sequential_refs_replaced_independently(self):
        result, names = replace_names_in_formula_xr(
            '{a} * {b}', computed_names={'a', 'b'})
        assert '_xr["a"]["a"]' in result
        assert '_xr["b"]["b"]' in result
        assert len(names) == 2
