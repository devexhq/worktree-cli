from __future__ import annotations

import json

import pytest

from tests.harness.assertions import assert_model_equal
from worktree.core.step.models import ConditionEvaluationResult, StepResult
from worktree.core.step.services.conditions import (
    ParsedCondition,
    evaluate_condition,
    parse_condition_expression,
    validate_condition_expression,
)

pytestmark = pytest.mark.unit

PARSER_OPERATOR_CASES = [
    pytest.param(
        "iteration.index == 1",
        ParsedCondition(raw="iteration.index == 1", left="iteration.index", operator="==", right="1"),
        id="eq",
    ),
    pytest.param(
        "iteration.index != 1",
        ParsedCondition(raw="iteration.index != 1", left="iteration.index", operator="!=", right="1"),
        id="ne",
    ),
    pytest.param(
        "iteration.index >= 1",
        ParsedCondition(raw="iteration.index >= 1", left="iteration.index", operator=">=", right="1"),
        id="ge",
    ),
    pytest.param(
        "iteration.index <= 1",
        ParsedCondition(raw="iteration.index <= 1", left="iteration.index", operator="<=", right="1"),
        id="le",
    ),
    pytest.param(
        "iteration.index > 1",
        ParsedCondition(raw="iteration.index > 1", left="iteration.index", operator=">", right="1"),
        id="gt",
    ),
    pytest.param(
        "iteration.index < 1",
        ParsedCondition(raw="iteration.index < 1", left="iteration.index", operator="<", right="1"),
        id="lt",
    ),
    pytest.param(
        "steps.build.stdout contains success",
        ParsedCondition(
            raw="steps.build.stdout contains success",
            left="steps.build.stdout",
            operator="contains",
            right="success",
        ),
        id="contains",
    ),
]

BOOLEAN_CASING_CASES = [
    pytest.param(
        "steps.check.outputs.ready == TRUE",
        ConditionEvaluationResult(
            expression="steps.check.outputs.ready == TRUE",
            passed=True,
            actual=True,
            expected=True,
            detail="TRUE",
        ),
        id="true_upper",
    ),
    pytest.param(
        "steps.check.outputs.ready == true",
        ConditionEvaluationResult(
            expression="steps.check.outputs.ready == true",
            passed=True,
            actual=True,
            expected=True,
            detail="TRUE",
        ),
        id="true_lower",
    ),
    pytest.param(
        "steps.check.outputs.ready == True",
        ConditionEvaluationResult(
            expression="steps.check.outputs.ready == True",
            passed=True,
            actual=True,
            expected=True,
            detail="TRUE",
        ),
        id="true_title",
    ),
    pytest.param(
        "steps.check.outputs.ready == FALSE",
        ConditionEvaluationResult(
            expression="steps.check.outputs.ready == FALSE",
            passed=False,
            actual=True,
            expected=False,
            detail="FALSE (was True)",
        ),
        id="false_upper",
    ),
    pytest.param(
        "steps.check.outputs.ready == false",
        ConditionEvaluationResult(
            expression="steps.check.outputs.ready == false",
            passed=False,
            actual=True,
            expected=False,
            detail="FALSE (was True)",
        ),
        id="false_lower",
    ),
    pytest.param(
        "steps.check.outputs.ready == False",
        ConditionEvaluationResult(
            expression="steps.check.outputs.ready == False",
            passed=False,
            actual=True,
            expected=False,
            detail="FALSE (was True)",
        ),
        id="false_title",
    ),
]


class ConditionExpressionParserTests:
    """Unit tests verifying parser behavior across all supported comparison operators."""

    @pytest.mark.parametrize(("expression", "expected"), PARSER_OPERATOR_CASES)
    def test_parse_condition_expression_supports_all_comparison_operators(
        self,
        expression: str,
        expected: ParsedCondition,
    ) -> None:
        """Verify each registered operator is recognized into a ParsedCondition structure."""
        assert parse_condition_expression(expression) == expected


class ConditionExpressionEvaluatorTests:
    """Unit tests verifying operand resolution and boolean evaluation contracts."""

    def test_evaluate_condition_resolves_nested_json_subpath_in_step_outputs(self) -> None:
        """Verify nested JSON subpath in prior step outputs resolves and evaluates correctly."""
        step_res = StepResult(
            step_id="build",
            status="completed",
            exit_code=0,
            stdout=json.dumps({"metrics": {"coverage": 85}}),
            stderr="",
            duration_seconds=0.1,
        )
        result = evaluate_condition(
            "steps.build.outputs.metrics.coverage >= 80",
            step_results={"build": step_res},
        )
        assert_model_equal(
            result,
            ConditionEvaluationResult(
                expression="steps.build.outputs.metrics.coverage >= 80",
                passed=True,
                actual=85,
                expected=80,
                detail="TRUE",
            ),
        )

    @pytest.mark.parametrize(("expression", "expected"), BOOLEAN_CASING_CASES)
    def test_evaluate_condition_parses_boolean_literals_case_insensitively(
        self,
        expression: str,
        expected: ConditionEvaluationResult,
    ) -> None:
        """Verify TRUE, True, true, FALSE, False, false literals evaluate case-insensitively."""
        step_res = StepResult(
            step_id="check",
            status="completed",
            exit_code=0,
            stdout=json.dumps({"ready": True}),
            stderr="",
            duration_seconds=0.1,
        )
        result = evaluate_condition(
            expression,
            step_results={"check": step_res},
        )
        assert_model_equal(result, expected)


class ConditionExpressionValidatorTests:
    """Unit tests verifying semantic validation of until condition expressions."""

    def test_validate_condition_expression_detects_unknown_step_ids(self) -> None:
        """Validation returns error diagnostic when condition references step not in known steps."""
        expression = "steps.unknown_step.exit_code == 0"
        errors = validate_condition_expression(expression, known_step_ids={"build"})
        assert errors == [
            "Step id 'unknown_step' referenced in until condition 'steps.unknown_step.exit_code == 0' not found in loop 'do' steps (allowed: build)."
        ]
