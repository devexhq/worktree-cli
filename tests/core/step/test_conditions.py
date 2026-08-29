"""Unit tests for condition expression parser, validator, and evaluator."""

from __future__ import annotations

import pytest

from worktree.core.step.models import StepResult
from worktree.core.step.services.conditions import (
    evaluate_condition,
    parse_condition_expression,
    parse_literal,
    validate_condition_expression,
)


class TestConditionParser:
    """Tests for parse_condition_expression."""

    @pytest.mark.parametrize(
        ("expr", "expected_left", "expected_op", "expected_right"),
        [
            ("steps.unit.exit_code == 0", "steps.unit.exit_code", "==", "0"),
            ("steps.eval.score >= 0.85", "steps.eval.score", ">=", "0.85"),
            ("steps.check.output contains success", "steps.check.output", "contains", "success"),
            ("steps.check.output contains 'hello world'", "steps.check.output", "contains", "'hello world'"),
            ('steps.check.output contains "hello world"', "steps.check.output", "contains", '"hello world"'),
            ("iteration.index > 3", "iteration.index", ">", "3"),
            ("steps.build.status != failed", "steps.build.status", "!=", "failed"),
            ("steps.test.exit_code <= 1", "steps.test.exit_code", "<=", "1"),
            ("steps.test.exit_code < 2", "steps.test.exit_code", "<", "2"),
        ],
    )
    def test_parse_valid_expressions(
        self,
        expr: str,
        expected_left: str,
        expected_op: str,
        expected_right: str,
    ) -> None:
        parsed = parse_condition_expression(expr)
        assert parsed is not None
        assert parsed.left == expected_left
        assert parsed.operator == expected_op
        assert parsed.right == expected_right

    @pytest.mark.parametrize(
        "expr",
        [
            "",
            "   ",
            "steps.unit.exit_code",
            "steps.unit.exit_code ==",
            "== 0",
            "steps.unit.exit_code === 0",
            "steps.unit.exit_code in ['a', 'b']",
            "steps.unit.exit_code ~ 0",
        ],
    )
    def test_parse_invalid_expressions(self, expr: str) -> None:
        assert parse_condition_expression(expr) is None


class TestConditionValidator:
    """Tests for validate_condition_expression."""

    def test_valid_step_reference_with_known_ids(self) -> None:
        errors = validate_condition_expression(
            "steps.unit.exit_code == 0",
            known_step_ids={"unit", "lint"},
        )
        assert errors == []

    def test_valid_iteration_reference(self) -> None:
        errors = validate_condition_expression(
            "iteration.index >= 3",
            known_step_ids={"unit"},
        )
        assert errors == []

    def test_unknown_step_id(self) -> None:
        errors = validate_condition_expression(
            "steps.missing.exit_code == 0",
            known_step_ids={"unit", "lint"},
        )
        assert len(errors) == 1
        assert "Step id 'missing'" in errors[0]

    def test_invalid_step_field(self) -> None:
        errors = validate_condition_expression(
            "steps.unit.nonexistent == 0",
            known_step_ids={"unit"},
        )
        assert len(errors) == 1
        assert "Unknown step field 'nonexistent'" in errors[0]

    def test_malformed_step_reference(self) -> None:
        errors = validate_condition_expression("steps.unit == 0")
        assert len(errors) == 1
        assert "Invalid step reference 'steps.unit'" in errors[0]

    def test_invalid_left_operand(self) -> None:
        errors = validate_condition_expression("random_var == 0")
        assert len(errors) == 1
        assert "must reference at least one dynamic operand" in errors[0]

    def test_valid_reversed_step_operand(self) -> None:
        errors = validate_condition_expression(
            "0 == steps.unit.exit_code",
            known_step_ids={"unit"},
        )
        assert errors == []

    def test_valid_reversed_iteration_operand(self) -> None:
        errors = validate_condition_expression("3 <= iteration.index")
        assert errors == []

    def test_both_static_operands_error(self) -> None:
        errors = validate_condition_expression("1 == 1")
        assert len(errors) == 1
        assert "must reference at least one dynamic operand" in errors[0]

    def test_valid_right_step_reference(self) -> None:
        errors = validate_condition_expression(
            "steps.lint.exit_code == steps.test.exit_code",
            known_step_ids={"lint", "test"},
        )
        assert errors == []

    def test_unknown_right_step_id(self) -> None:
        errors = validate_condition_expression(
            "steps.lint.exit_code == steps.missing.exit_code",
            known_step_ids={"lint", "test"},
        )
        assert len(errors) == 1
        assert "Step id 'missing'" in errors[0]

    def test_invalid_right_step_field(self) -> None:
        errors = validate_condition_expression(
            "steps.lint.exit_code == steps.test.nonexistent",
            known_step_ids={"lint", "test"},
        )
        assert len(errors) == 1
        assert "Unknown step field 'nonexistent'" in errors[0]

    def test_malformed_right_step_reference(self) -> None:
        errors = validate_condition_expression("steps.lint.exit_code == steps.test")
        assert len(errors) == 1
        assert "Invalid step reference 'steps.test'" in errors[0]

    def test_both_step_operands_with_errors(self) -> None:
        errors = validate_condition_expression(
            "steps.missing_a.exit_code == steps.missing_b.exit_code",
            known_step_ids={"unit"},
        )
        assert len(errors) == 2
        assert "Step id 'missing_a'" in errors[0]
        assert "Step id 'missing_b'" in errors[1]


class TestConditionEvaluator:
    """Tests for evaluate_condition."""

    def _make_step_result(
        self,
        step_id: str = "unit",
        *,
        status: str = "completed",
        exit_code: int = 0,
        stdout: str = "all tests passed",
        stderr: str = "",
    ) -> StepResult:
        return StepResult(
            step_id=step_id,
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=0.0,
        )

    def test_equality_integer(self) -> None:
        step_results = {"unit": self._make_step_result(exit_code=0)}
        res = evaluate_condition("steps.unit.exit_code == 0", iteration_index=1, step_results=step_results)
        assert res.passed is True
        assert res.actual == 0
        assert res.expected == 0

        res_fail = evaluate_condition("steps.unit.exit_code == 1", iteration_index=1, step_results=step_results)
        assert res_fail.passed is False
        assert res_fail.actual == 0

    def test_inequality(self) -> None:
        step_results = {"unit": self._make_step_result(exit_code=1)}
        res = evaluate_condition("steps.unit.exit_code != 0", iteration_index=1, step_results=step_results)
        assert res.passed is True

    def test_relational_operators(self) -> None:
        step_results = {"unit": self._make_step_result(exit_code=2)}
        assert (
            evaluate_condition("steps.unit.exit_code > 1", iteration_index=1, step_results=step_results).passed is True
        )
        assert (
            evaluate_condition("steps.unit.exit_code >= 2", iteration_index=1, step_results=step_results).passed is True
        )
        assert (
            evaluate_condition("steps.unit.exit_code < 3", iteration_index=1, step_results=step_results).passed is True
        )
        assert (
            evaluate_condition("steps.unit.exit_code <= 2", iteration_index=1, step_results=step_results).passed is True
        )
        assert (
            evaluate_condition("steps.unit.exit_code > 2", iteration_index=1, step_results=step_results).passed is False
        )

    def test_contains_operator(self) -> None:
        step_results = {"unit": self._make_step_result(stdout="tests passed with 100% coverage")}
        res_pass = evaluate_condition(
            "steps.unit.stdout contains '100% coverage'",
            iteration_index=1,
            step_results=step_results,
        )
        assert res_pass.passed is True

        res_fail = evaluate_condition(
            "steps.unit.stdout contains 'failure'",
            iteration_index=1,
            step_results=step_results,
        )
        assert res_fail.passed is False

    def test_iteration_index_evaluation(self) -> None:
        assert evaluate_condition("iteration.index == 3", iteration_index=3, step_results={}).passed is True
        assert evaluate_condition("iteration.index >= 3", iteration_index=2, step_results={}).passed is False
        assert evaluate_condition("iteration.index >= 3", iteration_index=3, step_results={}).passed is True

    def test_missing_step_result_evaluates_false(self) -> None:
        res = evaluate_condition("steps.unit.exit_code == 0", iteration_index=1, step_results={})
        assert res.passed is False
        assert res.actual is None
        assert "not found" in res.detail

    def test_step_to_step_equality(self) -> None:
        step_results = {
            "lint": self._make_step_result("lint", exit_code=0),
            "test": self._make_step_result("test", exit_code=0),
            "build": self._make_step_result("build", exit_code=1),
        }
        res_pass = evaluate_condition(
            "steps.lint.exit_code == steps.test.exit_code",
            iteration_index=1,
            step_results=step_results,
        )
        assert res_pass.passed is True
        assert res_pass.actual == 0
        assert res_pass.expected == 0

        res_fail = evaluate_condition(
            "steps.lint.exit_code == steps.build.exit_code",
            iteration_index=1,
            step_results=step_results,
        )
        assert res_fail.passed is False
        assert res_fail.actual == 0
        assert res_fail.expected == 1

    def test_step_to_step_comparison(self) -> None:
        step_results = {
            "lint": self._make_step_result("lint", exit_code=0),
            "test": self._make_step_result("test", exit_code=2),
        }
        res = evaluate_condition(
            "steps.lint.exit_code < steps.test.exit_code",
            iteration_index=1,
            step_results=step_results,
        )
        assert res.passed is True
        assert res.actual == 0
        assert res.expected == 2

    def test_string_status_equality(self) -> None:
        step_results = {
            "build": self._make_step_result("build", status="completed"),
            "deploy": self._make_step_result("deploy", status="completed"),
            "test": self._make_step_result("test", status="failed"),
        }
        assert (
            evaluate_condition(
                "steps.build.status == 'completed'",
                iteration_index=1,
                step_results=step_results,
            ).passed
            is True
        )
        assert (
            evaluate_condition(
                "steps.build.status == steps.deploy.status",
                iteration_index=1,
                step_results=step_results,
            ).passed
            is True
        )
        assert (
            evaluate_condition(
                "steps.build.status == steps.test.status",
                iteration_index=1,
                step_results=step_results,
            ).passed
            is False
        )
        assert (
            evaluate_condition(
                "steps.build.status != steps.test.status",
                iteration_index=1,
                step_results=step_results,
            ).passed
            is True
        )

    def test_missing_right_step_result_evaluates_false(self) -> None:
        step_results = {"lint": self._make_step_result("lint", exit_code=0)}
        res = evaluate_condition(
            "steps.lint.exit_code == steps.missing.exit_code",
            iteration_index=1,
            step_results=step_results,
        )
        assert res.passed is False
        assert res.actual == 0
        assert res.expected is None

    def test_missing_both_step_results_evaluates_false(self) -> None:
        res = evaluate_condition(
            "steps.a.exit_code == steps.b.exit_code",
            iteration_index=1,
            step_results={},
        )
        assert res.passed is False
        assert res.actual is None
        assert res.expected is None

    def test_outputs_json_path_resolution(self) -> None:
        step_results = {
            "eval": self._make_step_result(
                "eval",
                stdout='{"metrics": {"score": 95, "passed": true}}',
            ),
        }
        res = evaluate_condition(
            "steps.eval.outputs.metrics.score >= 90",
            iteration_index=1,
            step_results=step_results,
        )
        assert res.passed is True
        assert res.actual == 95
        assert res.expected == 90

    def test_outputs_invalid_json(self) -> None:
        step_results = {
            "eval": self._make_step_result("eval", stdout="not json"),
        }
        res = evaluate_condition(
            "steps.eval.outputs.score == 10",
            iteration_index=1,
            step_results=step_results,
        )
        assert res.passed is False
        assert res.actual is None

    def test_boolean_literal_evaluation(self) -> None:
        step_results = {
            "eval": self._make_step_result(
                "eval",
                stdout='{"passed": true}',
            ),
        }
        res = evaluate_condition(
            "steps.eval.outputs.passed == true",
            iteration_index=1,
            step_results=step_results,
        )
        assert res.passed is True
        assert res.actual is True
        assert res.expected is True

    def test_syntax_error_evaluation(self) -> None:
        res = evaluate_condition("not a valid expression", iteration_index=1, step_results={})
        assert res.passed is False
        assert "syntax error" in res.detail

    def test_invalid_syntax_validation(self) -> None:
        errors = validate_condition_expression("invalid syntax expression")
        assert len(errors) == 1
        assert "Invalid condition expression" in errors[0]

    def test_non_numeric_relational_comparison(self) -> None:
        step_results = {
            "build": self._make_step_result("build", stdout="text"),
        }
        res = evaluate_condition(
            "steps.build.stdout > 10",
            iteration_index=1,
            step_results=step_results,
        )
        assert res.passed is False

    def test_reversed_step_literal_evaluation(self) -> None:
        step_results = {"unit": self._make_step_result("unit", exit_code=0)}
        res = evaluate_condition("0 == steps.unit.exit_code", iteration_index=1, step_results=step_results)
        assert res.passed is True
        assert res.actual == 0
        assert res.expected == 0

    def test_reversed_iteration_evaluation(self) -> None:
        res = evaluate_condition("3 <= iteration.index", iteration_index=3, step_results={})
        assert res.passed is True
        assert res.actual == 3
        assert res.expected == 3


class TestParseLiteral:
    """Tests for parse_literal with ast-based parsing."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0", 0),
            ("42", 42),
            ("-10", -10),
            ("3.2", 3.2),
            ("-0.85", -0.85),
            ("1e-4", 0.0001),
            ("'hello'", "hello"),
            ('"hello"', "hello"),
            ("'it\\'s fine'", "it's fine"),
            ("true", True),
            ("false", False),
            ("True", True),
            ("False", False),
            ("TRUE", True),
            ("completed", "completed"),
            ("failed", "failed"),
            ("nan", "nan"),
            ("inf", "inf"),
            ("-inf", "-inf"),
            ("hello world", "hello world"),
            ("", ""),
        ],
    )
    def test_parse_literal_values(self, raw: str, expected: object) -> None:
        assert parse_literal(raw) == expected
