"""Unit tests for pure process/output assertion evaluators."""

from getworktree.core.step.assertions import (
    evaluate_exit_code,
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
