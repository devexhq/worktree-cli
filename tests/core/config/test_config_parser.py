"""Tests for typed value parser."""

from __future__ import annotations

import pytest

from getworktree.core.config.parser import parse_config_value


class TestParseConfigValue:
    """Unit tests for parse_config_value across supported types and edge cases."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("true", True),
            ("TRUE", True),
            ("True", True),
            ("false", False),
            ("FALSE", False),
            ("False", False),
            ("yes", True),
            ("YES", True),
            ("Yes", True),
            ("no", False),
            ("NO", False),
            ("No", False),
        ],
    )
    def test_fr1_boolean_parsing(self, input_val: str, expected: bool) -> None:
        result = parse_config_value(input_val)
        assert result is expected
        assert isinstance(result, bool)

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("0", 0),
            ("10", 10),
            ("-42", -42),
            ("999999", 999999),
        ],
    )
    def test_fr2_integer_parsing(self, input_val: str, expected: int) -> None:
        result = parse_config_value(input_val)
        assert result == expected
        assert isinstance(result, int)

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("3.14", 3.14),
            ("-0.001", -0.001),
            ("1e-5", 1e-5),
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
            "qwen2.5-coder",
            "hello world",
            "maybe",
            "http://localhost:11434",
            "v1.0.0",
        ],
    )
    def test_fr4_string_fallback(self, input_val: str) -> None:
        result = parse_config_value(input_val)
        assert result == input_val
        assert isinstance(result, str)

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ('"true"', "true"),
            ('"false"', "false"),
            ('"10"', "10"),
            ('"3.14"', "3.14"),
            ('"[1, 2]"', "[1, 2]"),
            ('"hello"', "hello"),
        ],
    )
    def test_fr5_explicit_string_preservation(
        self, input_val: str, expected: str
    ) -> None:
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
