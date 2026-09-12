"""Test harness primitives, shared builders, and contract assertions."""

from tests.harness.assertions import (
    ResultProtocol,
    assert_model_equal,
    assert_result_error,
    assert_result_ok,
)
from tests.harness.builders import (
    BlueprintBuilder,
    StepBuilder,
    WorkspaceBuilder,
)
from tests.harness.formatter import (
    FormatterCase,
    assert_json_payload_matches_published_shape,
    assert_rich_render_shows_every_view_value,
    assert_transform_derives_expected_view,
    render_rich,
)

__all__ = [
    "BlueprintBuilder",
    "FormatterCase",
    "ResultProtocol",
    "StepBuilder",
    "WorkspaceBuilder",
    "assert_json_payload_matches_published_shape",
    "assert_model_equal",
    "assert_result_error",
    "assert_result_ok",
    "assert_rich_render_shows_every_view_value",
    "assert_transform_derives_expected_view",
    "render_rich",
]
