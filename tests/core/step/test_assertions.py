"""Unit tests for pure process/output assertion evaluators."""

import json

from getworktree.core.step.assertions import (
    evaluate_exit_code,
    evaluate_json_match,
    evaluate_output_contains,
    evaluate_output_not_contains,
    evaluate_regex_match,
)


def test_evaluate_exit_code_pass_scalar():
    assert evaluate_exit_code(0, 0) == []


def test_evaluate_exit_code_pass_list():
    assert evaluate_exit_code([0, 1], 1) == []


def test_evaluate_exit_code_fail_scalar():
    assert evaluate_exit_code(0, 1) == ["exit_code: expected [0], got 1"]


def test_evaluate_exit_code_fail_list():
    assert evaluate_exit_code([0, 1], 2) == ["exit_code: expected [0, 1], got 2"]


def test_evaluate_exit_code_empty_expected_always_fails():
    assert evaluate_exit_code([], 0) == ["exit_code: expected [], got 0"]


def test_evaluate_output_contains_pass_scalar():
    assert evaluate_output_contains("ok", "status: ok\n") == []


def test_evaluate_output_contains_pass_list():
    assert evaluate_output_contains(["alpha", "beta"], "alpha\nbeta") == []


def test_evaluate_output_contains_fail_scalar():
    assert evaluate_output_contains("missing", "present") == [
        "output_contains: substring 'missing' not found in output"
    ]


def test_evaluate_output_contains_fail_list_preserves_order():
    assert evaluate_output_contains(["a", "b", "c"], "a and c") == [
        "output_contains: substring 'b' not found in output",
    ]


def test_evaluate_output_contains_multiple_failures_preserve_input_order():
    assert evaluate_output_contains(["foo", "bar", "z"], "only z") == [
        "output_contains: substring 'foo' not found in output",
        "output_contains: substring 'bar' not found in output",
    ]


def test_evaluate_output_contains_empty_string_is_always_found():
    assert evaluate_output_contains("", "any output") == []


def test_evaluate_output_not_contains_pass_scalar():
    assert evaluate_output_not_contains("error", "all good") == []


def test_evaluate_output_not_contains_pass_list():
    assert evaluate_output_not_contains(["error", "fail"], "all good") == []


def test_evaluate_output_not_contains_fail_scalar():
    assert evaluate_output_not_contains("error", "got error here") == [
        "output_not_contains: forbidden substring 'error' found in output"
    ]


def test_evaluate_output_not_contains_fail_list_preserves_order():
    assert evaluate_output_not_contains(["a", "b", "c"], "has b and a") == [
        "output_not_contains: forbidden substring 'a' found in output",
        "output_not_contains: forbidden substring 'b' found in output",
    ]


def test_evaluate_regex_match_pass():
    assert evaluate_regex_match(r"code=\d+", "code=42") == []


def test_evaluate_regex_match_fail_no_match():
    assert evaluate_regex_match(r"^done$", "not done") == ["regex_match: pattern '^done$' did not match output"]


def test_evaluate_regex_match_invalid_pattern():
    failures = evaluate_regex_match("(", "anything")
    assert len(failures) == 1
    assert failures[0].startswith("regex_match: invalid regex pattern '(': ")


def _json_stdout(payload: object) -> str:
    return json.dumps(payload)


def test_evaluate_json_match_invalid_json_empty_stdout():
    assert evaluate_json_match({"path": "a", "operator": "eq", "value": 1}, "") == ["json_match: Invalid JSON output"]


def test_evaluate_json_match_invalid_json_malformed_stdout():
    assert evaluate_json_match({"path": "a", "operator": "eq", "value": 1}, "not-json") == [
        "json_match: Invalid JSON output"
    ]


def test_evaluate_json_match_path_not_found_missing_key():
    stdout = _json_stdout({"summary": {"status": "ok"}})
    assert evaluate_json_match({"path": "summary.missing", "operator": "eq", "value": "ok"}, stdout) == [
        "json_match: JSON path 'summary.missing' not found"
    ]


def test_evaluate_json_match_path_not_found_list_root():
    assert evaluate_json_match({"path": "status", "operator": "eq", "value": 1}, _json_stdout([1, 2, 3])) == [
        "json_match: JSON path 'status' not found"
    ]


def test_evaluate_json_match_path_not_found_scalar_root():
    assert evaluate_json_match({"path": "status", "operator": "eq", "value": 1}, _json_stdout(42)) == [
        "json_match: JSON path 'status' not found"
    ]


def test_evaluate_json_match_path_not_found_non_dict_intermediate():
    stdout = _json_stdout({"summary": "ok"})
    assert evaluate_json_match({"path": "summary.status", "operator": "eq", "value": "ok"}, stdout) == [
        "json_match: JSON path 'summary.status' not found"
    ]


def test_evaluate_json_match_path_not_found_empty_path():
    stdout = _json_stdout({"a": 1})
    assert evaluate_json_match({"path": "", "operator": "eq", "value": 1}, stdout) == [
        "json_match: JSON path '' not found"
    ]


def test_evaluate_json_match_eq_pass():
    stdout = _json_stdout({"summary": {"status": "APPROVED"}})
    assert evaluate_json_match({"path": "summary.status", "operator": "eq", "value": "APPROVED"}, stdout) == []


def test_evaluate_json_match_eq_fail():
    stdout = _json_stdout({"summary": {"status": "APPROVED"}})
    assert evaluate_json_match({"path": "summary.status", "operator": "eq", "value": "DENIED"}, stdout) == [
        "json_match: 'summary.status' was 'APPROVED', expected 'DENIED'"
    ]


def test_evaluate_json_match_eq_null_pass():
    stdout = _json_stdout({"result": None})
    assert evaluate_json_match({"path": "result", "operator": "eq", "value": None}, stdout) == []


def test_evaluate_json_match_eq_null_fail():
    stdout = _json_stdout({"result": None})
    assert evaluate_json_match({"path": "result", "operator": "eq", "value": "x"}, stdout) == [
        "json_match: 'result' was None, expected 'x'"
    ]


def test_evaluate_json_match_neq_pass():
    stdout = _json_stdout({"count": 3})
    assert evaluate_json_match({"path": "count", "operator": "neq", "value": 0}, stdout) == []


def test_evaluate_json_match_neq_fail():
    stdout = _json_stdout({"count": 3})
    assert evaluate_json_match({"path": "count", "operator": "neq", "value": 3}, stdout) == [
        "json_match: 'count' was 3, expected not 3"
    ]


def test_evaluate_json_match_gt_pass():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "gt", "value": 4}, stdout) == []


def test_evaluate_json_match_gt_fail():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "gt", "value": 5}, stdout) == [
        "json_match: 'n' was 5, expected greater than 5"
    ]


def test_evaluate_json_match_gte_pass():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "gte", "value": 5}, stdout) == []


def test_evaluate_json_match_gte_fail():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "gte", "value": 6}, stdout) == [
        "json_match: 'n' was 5, expected at least 6"
    ]


def test_evaluate_json_match_lt_pass():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "lt", "value": 6}, stdout) == []


def test_evaluate_json_match_lt_fail():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "lt", "value": 5}, stdout) == [
        "json_match: 'n' was 5, expected less than 5"
    ]


def test_evaluate_json_match_lte_pass():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "lte", "value": 5}, stdout) == []


def test_evaluate_json_match_lte_fail():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "lte", "value": 4}, stdout) == [
        "json_match: 'n' was 5, expected at most 4"
    ]


def test_evaluate_json_match_contains_list_pass():
    stdout = _json_stdout({"tags": ["a", "b"]})
    assert evaluate_json_match({"path": "tags", "operator": "contains", "value": "a"}, stdout) == []


def test_evaluate_json_match_contains_string_pass():
    stdout = _json_stdout({"name": "alpha"})
    assert evaluate_json_match({"path": "name", "operator": "contains", "value": "ph"}, stdout) == []


def test_evaluate_json_match_contains_fail():
    stdout = _json_stdout({"tags": ["a", "b"]})
    assert evaluate_json_match({"path": "tags", "operator": "contains", "value": "z"}, stdout) == [
        "json_match: 'tags' does not contain 'z' (was ['a', 'b'])"
    ]


def test_evaluate_json_match_contains_type_error_treated_as_failure():
    stdout = _json_stdout({"n": 42})
    assert evaluate_json_match({"path": "n", "operator": "contains", "value": 4}, stdout) == [
        "json_match: 'n' does not contain 4 (was 42)"
    ]


def test_evaluate_json_match_eq_truncates_long_strings():
    # Generated failure message looks like:
    # json_match: 'blob' was 'AAAA[491 chars]AAAAAMISMATCHBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB[463 chars]BBBB',
    # expected 'AAAA[491 chars]AAAAAPERFECTBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB[462 chars]BBBB'
    actual = "A" * 500 + "MISMATCH" + "B" * 500
    expected = "A" * 500 + "PERFECT" + "B" * 500
    stdout = _json_stdout({"blob": actual})
    failures = evaluate_json_match({"path": "blob", "operator": "eq", "value": expected}, stdout)
    assert len(failures) == 1
    message = failures[0]
    assert message.startswith("json_match: 'blob' was ")
    assert ", expected " in message
    assert "[491 chars]" in message
    assert "MISMATCH" in message
    assert "PERFECT" in message
    assert actual not in message
    assert expected not in message


def test_evaluate_json_match_eq_truncates_long_object_values():
    # Generated failure message looks like:
    # json_match: 'payload' was {'key[532 chars]AAAAAMISMATCHBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB[464 chars]BBB'},
    # expected {'key[532 chars]AAAAAPERFECTBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB[463 chars]BBB'}
    actual = {"key_1": "constant", "large_value_key": "A" * 500 + "MISMATCH" + "B" * 500}
    expected = {"key_1": "constant", "large_value_key": "A" * 500 + "PERFECT" + "B" * 500}
    stdout = _json_stdout({"payload": actual})
    failures = evaluate_json_match({"path": "payload", "operator": "eq", "value": expected}, stdout)
    assert len(failures) == 1
    message = failures[0]
    assert message.startswith("json_match: 'payload' was ")
    assert "chars]" in message
    assert "MISMATCH" in message
    assert "PERFECT" in message
    assert "A" * 100 not in message


def test_evaluate_json_match_contains_truncates_long_actual():
    # Generated failure message looks like:
    # json_match: 'blob' does not contain 'missing'
    # (was 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA [truncated]...)
    actual = "A" * 500 + "NEEDLE" + "B" * 500
    stdout = _json_stdout({"blob": actual})
    failures = evaluate_json_match({"path": "blob", "operator": "contains", "value": "missing"}, stdout)
    assert len(failures) == 1
    message = failures[0]
    assert "does not contain 'missing'" in message
    assert "[truncated]..." in message
    assert actual not in message


def test_evaluate_json_match_ordering_rejects_bool_actual():
    stdout = _json_stdout({"flag": True})
    assert evaluate_json_match({"path": "flag", "operator": "gt", "value": 0}, stdout) == [
        "json_match: operator 'gt' requires numeric values, got bool and int"
    ]


def test_evaluate_json_match_ordering_rejects_str_actual():
    stdout = _json_stdout({"label": "x"})
    assert evaluate_json_match({"path": "label", "operator": "lte", "value": 1}, stdout) == [
        "json_match: operator 'lte' requires numeric values, got str and int"
    ]


def test_evaluate_json_match_ordering_rejects_str_value():
    stdout = _json_stdout({"n": 5})
    assert evaluate_json_match({"path": "n", "operator": "gt", "value": "3"}, stdout) == [
        "json_match: operator 'gt' requires numeric values, got int and str"
    ]


def test_evaluate_json_match_ordering_rejects_bool_value():
    stdout = _json_stdout({"flag": True})
    assert evaluate_json_match({"path": "flag", "operator": "lt", "value": False}, stdout) == [
        "json_match: operator 'lt' requires numeric values, got bool and bool"
    ]


def test_evaluate_json_match_unsupported_operator():
    stdout = _json_stdout({"a": 1})
    assert evaluate_json_match({"path": "a", "operator": "regex", "value": 1}, stdout) == [
        "json_match: unsupported operator 'regex'"
    ]
