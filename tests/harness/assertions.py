"""Standardized contract assertion helpers for tests."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class ResultProtocol(Protocol):
    """Protocol for operation result objects exposing ok and errors."""

    @property
    def ok(self) -> bool:
        """Return True when the operation succeeded without fatal errors."""
        ...

    @property
    def errors(self) -> list[str]:
        """Return list of error messages."""
        ...


def assert_result_ok(
    result: ResultProtocol,
    expected_status: object | None = None,
) -> None:
    """Assert that an operation result represents a successful outcome.

    Args:
        result: Result object conforming to ResultProtocol.
        expected_status: Optional expected status enum or value to assert against.

    Raises:
        AssertionError: If result.ok is False, errors exist, or status mismatches.
    """
    assert result.ok is True, f"Expected ok=True, got errors: {result.errors}"
    assert len(result.errors) == 0, f"Expected no errors, got: {result.errors}"

    if expected_status is not None:
        actual_status = getattr(result, "status", None)
        assert actual_status == expected_status, f"Expected status {expected_status!r}, got {actual_status!r}"


def assert_result_error(
    result: ResultProtocol,
    expected_code: str | None = None,
    *,
    expected_status: object | None = None,
) -> None:
    """Assert that an operation result represents an error outcome.

    Args:
        result: Result object conforming to ResultProtocol.
        expected_code: Optional substring or error code expected in result.errors.
        expected_status: Optional expected status enum or value to assert against.

    Raises:
        AssertionError: If result.ok is True, errors is empty, or code/status mismatches.
    """
    assert result.ok is False, "Expected ok=False, got ok=True"
    assert len(result.errors) > 0, "Expected non-empty errors list"

    if expected_status is not None:
        actual_status = getattr(result, "status", None)
        assert actual_status == expected_status, f"Expected status {expected_status!r}, got {actual_status!r}"

    if expected_code is not None:
        found = any(expected_code in str(err) or getattr(err, "code", None) == expected_code for err in result.errors)
        assert found, f"Expected error code or substring {expected_code!r} in {result.errors}"


def _assert_model_vs_model(
    actual: BaseModel,
    expected: BaseModel,
    exclude: set[str] | None,
) -> None:
    if exclude is not None:
        assert actual.model_dump(mode="json", exclude=exclude) == expected.model_dump(mode="json", exclude=exclude)
        return

    assert actual == expected


def _assert_model_vs_dict(
    actual: BaseModel,
    expected: dict[str, Any],
    exclude: set[str] | None,
) -> None:
    expected_dict = {k: v for k, v in expected.items() if k not in exclude} if exclude is not None else expected
    assert actual.model_dump(mode="json", exclude=exclude) == expected_dict


def assert_model_equal(
    actual: BaseModel,
    expected: BaseModel | dict[str, Any],
    *,
    exclude: set[str] | None = None,
) -> None:
    """Assert whole-object equality between actual model and expected model or dict.

    Args:
        actual: Live Pydantic model instance under test.
        expected: Target BaseModel instance or dictionary representation.
        exclude: Optional set of field names to exclude from comparison.

    Raises:
        AssertionError: If actual and expected models or dictionaries differ.
    """
    if isinstance(expected, BaseModel):
        _assert_model_vs_model(actual, expected, exclude)
    else:
        _assert_model_vs_dict(actual, expected, exclude)
