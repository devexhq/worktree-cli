"""Test harness primitives, shared builders, and contract assertions."""

from tests.harness.assertions import (
    ResultProtocol,
    assert_model_equal,
    assert_result_error,
    assert_result_ok,
)

__all__ = [
    "ResultProtocol",
    "assert_model_equal",
    "assert_result_error",
    "assert_result_ok",
]
