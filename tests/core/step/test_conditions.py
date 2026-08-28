"""Unit tests for condition expression parser, validator, and evaluator."""

from __future__ import annotations

import pytest

from worktree.core.step.models import StepResult
from worktree.core.step.services.conditions import (
    evaluate_condition,
    parse_condition_expression,
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
        assert "Condition left operand 'random_var' must reference" in errors[0]


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
