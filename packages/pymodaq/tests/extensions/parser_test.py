import pytest

from pymodaq.extensions.data_mixer.parser import (
    parse_named_formulae,
    extract_formula_output_names,
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
