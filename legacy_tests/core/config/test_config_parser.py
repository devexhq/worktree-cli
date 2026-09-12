"""Tests for typed value parser."""

from __future__ import annotations

import pytest

from worktree.core.config.parser import parse_config_value


class TestParseConfigValue:
    """Unit tests for parse_config_value across supported types and edge cases."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            pytest.param("true", True, id="lower_true"),
            pytest.param("TRUE", True, id="upper_true"),
            pytest.param("True", True, id="title_true"),
            pytest.param("false", False, id="lower_false"),
            pytest.param("FALSE", False, id="upper_false"),
            pytest.param("False", False, id="title_false"),
            pytest.param("yes", True, id="lower_yes"),
            pytest.param("YES", True, id="upper_yes"),
            pytest.param("Yes", True, id="title_yes"),
            pytest.param("no", False, id="lower_no"),
            pytest.param("NO", False, id="upper_no"),
            pytest.param("No", False, id="title_no"),
        ],
    )
    def test_fr1_boolean_parsing(self, input_val: str, expected: bool) -> None:
        result = parse_config_value(input_val)
        assert result is expected
        assert isinstance(result, bool)

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            pytest.param("0", 0, id="zero"),
            pytest.param("10", 10, id="positive_int"),
            pytest.param("-42", -42, id="negative_int"),
            pytest.param("999999", 999999, id="large_int"),
        ],
    )
    def test_fr2_integer_parsing(self, input_val: str, expected: int) -> None:
        result = parse_config_value(input_val)
        assert result == expected
        assert isinstance(result, int)

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            pytest.param("3.14", 3.14, id="pi_decimal"),
            pytest.param("-0.001", -0.001, id="negative_decimal"),
            pytest.param("1e-5", 1e-5, id="scientific_notation"),
        ],
    )
    def test_fr2_float_parsing(self, input_val: str, expected: float) -> None:
        result = parse_config_value(input_val)
        assert result == expected
        assert isinstance(result, float)

    def test_fr3_json_list_parsing(self) -> None:
        result = parse_config_value('[1, "a", true]')
        assert result == [1, "a", True]
        assert isinstance(result, list)

    def test_fr3_json_dict_parsing(self) -> None:
        result = parse_config_value('{"key": "val", "num": 42}')
        assert result == {"key": "val", "num": 42}
        assert isinstance(result, dict)

    def test_fr3_invalid_json_collection_falls_back_to_str(self) -> None:
        result = parse_config_value("[1, 2, unquoted]")
        assert result == "[1, 2, unquoted]"
        assert isinstance(result, str)

        result_dict = parse_config_value("{invalid json}")
        assert result_dict == "{invalid json}"
        assert isinstance(result_dict, str)

    @pytest.mark.parametrize(
        "input_val",
        [
            pytest.param("qwen2.5-coder", id="model_name"),
            pytest.param("hello world", id="phrase_with_space"),
            pytest.param("maybe", id="arbitrary_word"),
            pytest.param("http://localhost:11434", id="url_string"),
            pytest.param("v1.0.0", id="version_tag"),
        ],
    )
    def test_fr4_string_fallback(self, input_val: str) -> None:
        result = parse_config_value(input_val)
        assert result == input_val
        assert isinstance(result, str)

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            pytest.param('"true"', "true", id="quoted_bool_true"),
            pytest.param('"false"', "false", id="quoted_bool_false"),
            pytest.param('"10"', "10", id="quoted_int"),
            pytest.param('"3.14"', "3.14", id="quoted_float"),
            pytest.param('"[1, 2]"', "[1, 2]", id="quoted_list"),
            pytest.param('"hello"', "hello", id="quoted_string"),
        ],
    )
    def test_fr5_explicit_string_preservation(self, input_val: str, expected: str) -> None:
        result = parse_config_value(input_val)
        assert result == expected
        assert isinstance(result, str)

    def test_nfr1_deterministic_evaluation_order(self) -> None:
        # Explicit quotes override boolean parsing
        assert parse_config_value('"true"') == "true"
        assert type(parse_config_value('"true"')) is str

        # Explicit quotes override integer parsing
        assert parse_config_value('"100"') == "100"
        assert type(parse_config_value('"100"')) is str

        # Integer parsing takes precedence over float parsing for int strings
        assert type(parse_config_value("10")) is int

        # Float parsing handles decimal strings
        assert type(parse_config_value("10.5")) is float
