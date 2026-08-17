"""Unit tests for the json_match assertion evaluator."""

import json
from typing import Any

from worktree.core.step.assertions import evaluate_json_match


def _json_stdout(payload: object) -> str:
    return json.dumps(payload)


def _match(path: str, operator: str, value: Any, payload: object) -> list[str]:
    """Evaluate ``json_match`` against JSON-encoded ``payload``."""
    return evaluate_json_match({"path": path, "operator": operator, "value": value}, _json_stdout(payload))


class TestEvaluateJsonMatchParseAndPath:
    def test_invalid_json_empty_stdout(self):
        assert evaluate_json_match({"path": "a", "operator": "eq", "value": 1}, "") == [
            "json_match: Invalid JSON output"
        ]

    def test_invalid_json_malformed_stdout(self):
        assert evaluate_json_match({"path": "a", "operator": "eq", "value": 1}, "not-json") == [
            "json_match: Invalid JSON output"
        ]

    def test_path_not_found_missing_key(self):
        assert _match("summary.missing", "eq", "ok", {"summary": {"status": "ok"}}) == [
            "json_match: JSON path 'summary.missing' not found"
        ]

    def test_path_not_found_list_root(self):
        assert _match("status", "eq", 1, [1, 2, 3]) == ["json_match: JSON path 'status' not found"]

    def test_path_not_found_scalar_root(self):
        assert _match("status", "eq", 1, 42) == ["json_match: JSON path 'status' not found"]

    def test_path_not_found_non_dict_intermediate(self):
        assert _match("summary.status", "eq", "ok", {"summary": "ok"}) == [
            "json_match: JSON path 'summary.status' not found"
        ]

    def test_path_not_found_empty_path(self):
        assert _match("", "eq", 1, {"a": 1}) == ["json_match: JSON path '' not found"]


class TestEvaluateJsonMatchOperators:
    def test_eq_pass(self):
        assert _match("summary.status", "eq", "APPROVED", {"summary": {"status": "APPROVED"}}) == []

    def test_eq_fail(self):
        assert _match("summary.status", "eq", "DENIED", {"summary": {"status": "APPROVED"}}) == [
            "json_match: 'summary.status' was 'APPROVED', expected 'DENIED'"
        ]

    def test_eq_null_pass(self):
        assert _match("result", "eq", None, {"result": None}) == []

    def test_eq_null_fail(self):
        assert _match("result", "eq", "x", {"result": None}) == ["json_match: 'result' was None, expected 'x'"]

    def test_neq_pass(self):
        assert _match("count", "neq", 0, {"count": 3}) == []

    def test_neq_fail(self):
        assert _match("count", "neq", 3, {"count": 3}) == ["json_match: 'count' was 3, expected not 3"]

    def test_gt_pass(self):
        assert _match("n", "gt", 4, {"n": 5}) == []

    def test_gt_fail(self):
        assert _match("n", "gt", 5, {"n": 5}) == ["json_match: 'n' was 5, expected greater than 5"]

    def test_gte_pass(self):
        assert _match("n", "gte", 5, {"n": 5}) == []

    def test_gte_fail(self):
        assert _match("n", "gte", 6, {"n": 5}) == ["json_match: 'n' was 5, expected at least 6"]

    def test_lt_pass(self):
        assert _match("n", "lt", 6, {"n": 5}) == []

    def test_lt_fail(self):
        assert _match("n", "lt", 5, {"n": 5}) == ["json_match: 'n' was 5, expected less than 5"]

    def test_lte_pass(self):
        assert _match("n", "lte", 5, {"n": 5}) == []

    def test_lte_fail(self):
        assert _match("n", "lte", 4, {"n": 5}) == ["json_match: 'n' was 5, expected at most 4"]

    def test_contains_list_pass(self):
        assert _match("tags", "contains", "a", {"tags": ["a", "b"]}) == []

    def test_contains_string_pass(self):
        assert _match("name", "contains", "ph", {"name": "alpha"}) == []

    def test_contains_fail(self):
        assert _match("tags", "contains", "z", {"tags": ["a", "b"]}) == [
            "json_match: 'tags' does not contain 'z' (was ['a', 'b'])"
        ]

    def test_contains_type_error_treated_as_failure(self):
        assert _match("n", "contains", 4, {"n": 42}) == ["json_match: 'n' does not contain 4 (was 42)"]

    def test_unsupported_operator(self):
        assert _match("a", "regex", 1, {"a": 1}) == ["json_match: unsupported operator 'regex'"]


class TestEvaluateJsonMatchTruncation:
    def test_eq_truncates_long_strings(self):
        # Generated failure message looks like:
        # json_match: 'blob' was 'AAAA[491 chars]AAAAAMISMATCH...[463 chars]BBBB',
        # expected 'AAAA[491 chars]AAAAAPERFECT...[462 chars]BBBB'
        actual = "A" * 500 + "MISMATCH" + "B" * 500
        expected = "A" * 500 + "PERFECT" + "B" * 500
        failures = _match("blob", "eq", expected, {"blob": actual})
        assert len(failures) == 1
        message = failures[0]
        assert message.startswith("json_match: 'blob' was ")
        assert ", expected " in message
        assert "[491 chars]" in message
        assert "MISMATCH" in message
        assert "PERFECT" in message
        assert actual not in message
        assert expected not in message

    def test_eq_truncates_long_object_values(self):
        actual = {"key_1": "constant", "large_value_key": "A" * 500 + "MISMATCH" + "B" * 500}
        expected = {"key_1": "constant", "large_value_key": "A" * 500 + "PERFECT" + "B" * 500}
        failures = _match("payload", "eq", expected, {"payload": actual})
        assert len(failures) == 1
        message = failures[0]
        assert message.startswith("json_match: 'payload' was ")
        assert "chars]" in message
        assert "MISMATCH" in message
        assert "PERFECT" in message
        assert "A" * 100 not in message

    def test_contains_truncates_long_actual(self):
        actual = "A" * 500 + "NEEDLE" + "B" * 500
        failures = _match("blob", "contains", "missing", {"blob": actual})
        assert len(failures) == 1
        message = failures[0]
        assert "does not contain 'missing'" in message
        assert "[truncated]..." in message
        assert actual not in message


class TestEvaluateJsonMatchOrderingTypes:
    def test_rejects_bool_actual(self):
        assert _match("flag", "gt", 0, {"flag": True}) == [
            "json_match: operator 'gt' requires numeric values, got bool and int"
        ]

    def test_rejects_str_actual(self):
        assert _match("label", "lte", 1, {"label": "x"}) == [
            "json_match: operator 'lte' requires numeric values, got str and int"
        ]

    def test_rejects_str_value(self):
        assert _match("n", "gt", "3", {"n": 5}) == [
            "json_match: operator 'gt' requires numeric values, got int and str"
        ]

    def test_rejects_bool_value(self):
        assert _match("flag", "lt", False, {"flag": True}) == [
            "json_match: operator 'lt' requires numeric values, got bool and bool"
        ]
