"""Test harness primitives, shared builders, and contract assertions."""

from tests.harness.builders import (
    AgentRequestBuilder,
    BlueprintBuilder,
    DetectionResultBuilder,
    PruneResultBuilder,
    RunOutcomeBuilder,
    StatusBuilder,
    StepBuilder,
    WorkspaceBuilder,
)
from tests.harness.fakes import FakeAgentRunner, FakeAgentRunnerCall
from tests.harness.formatter import (
    FormatterCase,
    assert_json_payload_matches_published_shape,
    assert_rich_render_shows_every_view_value,
    assert_transform_derives_expected_view,
    render_rich,
)

__all__ = [
    "AgentRequestBuilder",
    "BlueprintBuilder",
    "DetectionResultBuilder",
    "FakeAgentRunner",
    "FakeAgentRunnerCall",
    "FormatterCase",
    "PruneResultBuilder",
    "RunOutcomeBuilder",
    "StatusBuilder",
    "StepBuilder",
    "WorkspaceBuilder",
    "assert_json_payload_matches_published_shape",
    "assert_rich_render_shows_every_view_value",
    "assert_transform_derives_expected_view",
    "render_rich",
]
