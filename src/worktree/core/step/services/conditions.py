"""Condition expression parser, validator, and evaluator for loop 'until' clauses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from worktree.core.step.models import ConditionEvaluationResult, StepResult

_CONDITION_RE = re.compile(r"^\s*(?P<left>.+?)\s*(?P<op>==|!=|>=|<=|>|<|\bcontains\b)\s*(?P<right>.+?)\s*$")
_VALID_OPERATORS = frozenset({"==", "!=", ">=", "<=", ">", "<", "contains"})
_ORDERED_OPERATORS = frozenset({">=", "<=", ">", "<"})
_VALID_STEP_FIELDS = frozenset({"exit_code", "outputs", "status", "stdout"})


@dataclass(frozen=True)
class ParsedCondition:
    """Structured representation of a parsed comparison condition."""

    raw: str
    left: str
    operator: str
    right: str


def parse_condition_expression(expression: str) -> ParsedCondition | None:
    """Parse a condition expression string into a ParsedCondition, or None if malformed."""
    match = _CONDITION_RE.match(expression.strip())
    if not match:
        return None
    left = match.group("left").strip()
    op = match.group("op").strip()
    right = match.group("right").strip()
    if not left or not right or op not in _VALID_OPERATORS or right.startswith("="):
        return None
    return ParsedCondition(raw=expression, left=left, operator=op, right=right)


def parse_literal(raw: str) -> Any:
    """Parse a literal value from a condition operand string."""
    token = raw.strip()
    if (token.startswith("'") and token.endswith("'")) or (token.startswith('"') and token.endswith('"')):
        return token[1:-1]
    if token.lower() == "true":
        return True
    if token.lower() == "false":
        return False
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return token


def _is_numeric(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _resolve_json_path(root: Any, path: list[str]) -> Any:
    current = root
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def _resolve_step_field(result: StepResult, field: str, subpath: list[str]) -> Any:
    if field == "exit_code":
        return result.exit_code
    if field == "status":
        return result.status
    if field == "stdout":
        return result.stdout
    if field == "outputs":
        try:
            parsed = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            return None
        if not subpath:
            return parsed
        return _resolve_json_path(parsed, subpath)
    return None


def resolve_operand_value(
    operand: str,
    *,
    iteration_index: int = 1,
    step_results: dict[str, StepResult] | None = None,
) -> Any:
    """Resolve an operand value against iteration index and step results."""
    token = operand.strip()
    if token in ("iteration.index", "iteration.attempt", "iteration"):
        return iteration_index

    if token.startswith("steps."):
        parts = token.split(".")
        if len(parts) >= 3:
            step_id = parts[1]
            field = parts[2]
            subpath = parts[3:]
            results = step_results or {}
            step_res = results.get(step_id)
            if step_res is None:
                return None
            return _resolve_step_field(step_res, field, subpath)

    return parse_literal(token)


def _compare_ordered(actual: Any, expected: Any, operator: str) -> bool:
    if not _is_numeric(actual) or not _is_numeric(expected):
        return False
    if operator == ">":
        return actual > expected
    if operator == "<":
        return actual < expected
    if operator == ">=":
        return actual >= expected
    if operator == "<=":
        return actual <= expected
    return False


def _compare_contains(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return False
    if isinstance(actual, str):
        return str(expected) in actual
    if isinstance(actual, (list, dict, set, tuple)):
        return expected in actual
    return str(expected) in str(actual)


def _compare_values(actual: Any, expected: Any, operator: str) -> bool:
    """Evaluate comparison between actual and expected values under operator."""
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if operator == "contains":
        return _compare_contains(actual, expected)
    if operator in _ORDERED_OPERATORS:
        return _compare_ordered(actual, expected, operator)
    return False


def _format_condition_detail(passed: bool, actual: Any) -> str:
    if passed:
        return "TRUE"
    if actual is None:
        return "FALSE (not found)"
    return f"FALSE (was {actual!r})"


def evaluate_condition(
    expression: str,
    *,
    iteration_index: int = 1,
    step_results: dict[str, StepResult] | None = None,
) -> ConditionEvaluationResult:
    """Parse and evaluate a single condition expression."""
    parsed = parse_condition_expression(expression)
    if parsed is None:
        return ConditionEvaluationResult(
            expression=expression,
            passed=False,
            actual=None,
            expected=None,
            detail="FALSE (syntax error)",
        )

    actual = resolve_operand_value(
        parsed.left,
        iteration_index=iteration_index,
        step_results=step_results,
    )
    expected = parse_literal(parsed.right)
    passed = _compare_values(actual, expected, parsed.operator)
    detail = _format_condition_detail(passed, actual)

    return ConditionEvaluationResult(
        expression=expression,
        passed=passed,
        actual=actual,
        expected=expected,
        detail=detail,
    )


def _validate_step_operand(
    left: str,
    expression: str,
    known_step_ids: set[str] | None,
) -> list[str]:
    parts = left.split(".")
    if len(parts) < 3:
        return [f"Invalid step reference '{left}' in condition. Expected 'steps.<step_id>.<field>'."]

    step_id, field = parts[1], parts[2]
    errors: list[str] = []
    if known_step_ids is not None and step_id not in known_step_ids:
        allowed = ", ".join(sorted(known_step_ids)) or "none"
        errors.append(
            f"Step id '{step_id}' referenced in until condition '{expression}' "
            f"not found in loop 'do' steps (allowed: {allowed})."
        )
    if field not in _VALID_STEP_FIELDS:
        errors.append(
            f"Unknown step field '{field}' in '{left}'. Allowed fields: {', '.join(sorted(_VALID_STEP_FIELDS))}."
        )
    return errors


def _validate_left_operand(
    left: str,
    expression: str,
    known_step_ids: set[str] | None,
) -> list[str]:
    if left.startswith("steps."):
        return _validate_step_operand(left, expression, known_step_ids)
    if left.startswith("iteration.") or left in ("iteration",):
        return []
    return [f"Condition left operand '{left}' must reference 'steps.<id>.<field>' or 'iteration.index'."]


def validate_condition_expression(
    expression: str,
    known_step_ids: set[str] | None = None,
) -> list[str]:
    """Validate syntax and step reference of an until condition expression.

    Returns a list of error message strings (empty if valid).
    """
    parsed = parse_condition_expression(expression)
    if parsed is None:
        return [
            f"Invalid condition expression '{expression}'. "
            f"Expected '<operand> <operator> <literal>' with operators: {', '.join(sorted(_VALID_OPERATORS))}."
        ]
    return _validate_left_operand(parsed.left, expression, known_step_ids)
