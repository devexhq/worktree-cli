"""Standardized contract assertion helpers for tests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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
