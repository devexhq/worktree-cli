"""Unit tests for process/output assertion evaluators."""

from worktree.core.step.assertions import (
    evaluate_exit_code,
    evaluate_output_contains,
    evaluate_output_not_contains,
    evaluate_regex_match,
)


class TestEvaluateExitCode:
    def test_pass_scalar(self):
        assert evaluate_exit_code(0, 0) == []

    def test_pass_list(self):
        assert evaluate_exit_code([0, 1], 1) == []

    def test_fail_scalar(self):
        assert evaluate_exit_code(0, 1) == ["exit_code: expected [0], got 1"]

    def test_fail_list(self):
        assert evaluate_exit_code([0, 1], 2) == ["exit_code: expected [0, 1], got 2"]

    def test_empty_expected_always_fails(self):
        assert evaluate_exit_code([], 0) == ["exit_code: expected [], got 0"]


class TestEvaluateOutputContains:
    def test_pass_scalar(self):
        assert evaluate_output_contains("ok", "status: ok\n") == []

    def test_pass_list(self):
        assert evaluate_output_contains(["alpha", "beta"], "alpha\nbeta") == []

    def test_fail_scalar(self):
        assert evaluate_output_contains("missing", "present") == [
            "output_contains: substring 'missing' not found in output"
        ]

    def test_fail_list_preserves_order(self):
        assert evaluate_output_contains(["a", "b", "c"], "a and c") == [
            "output_contains: substring 'b' not found in output",
        ]

    def test_multiple_failures_preserve_input_order(self):
        assert evaluate_output_contains(["foo", "bar", "z"], "only z") == [
            "output_contains: substring 'foo' not found in output",
            "output_contains: substring 'bar' not found in output",
        ]

    def test_empty_string_is_always_found(self):
        assert evaluate_output_contains("", "any output") == []


class TestEvaluateOutputNotContains:
    def test_pass_scalar(self):
        assert evaluate_output_not_contains("error", "all good") == []

    def test_pass_list(self):
        assert evaluate_output_not_contains(["error", "fail"], "all good") == []

    def test_fail_scalar(self):
        assert evaluate_output_not_contains("error", "got error here") == [
            "output_not_contains: forbidden substring 'error' found in output"
        ]

    def test_fail_list_preserves_order(self):
        assert evaluate_output_not_contains(["a", "b", "c"], "has b and a") == [
            "output_not_contains: forbidden substring 'a' found in output",
            "output_not_contains: forbidden substring 'b' found in output",
        ]


class TestEvaluateRegexMatch:
    def test_pass(self):
        assert evaluate_regex_match(r"code=\d+", "code=42") == []

    def test_fail_no_match(self):
        assert evaluate_regex_match(r"^done$", "not done") == ["regex_match: pattern '^done$' did not match output"]

    def test_invalid_pattern(self):
        failures = evaluate_regex_match("(", "anything")
        assert len(failures) == 1
        assert failures[0].startswith("regex_match: invalid regex pattern '(': ")
