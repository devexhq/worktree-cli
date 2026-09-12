"""Tier 2 presentation contract tests for RunSuccessFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.events import RunSuccessEvent
from worktree.cli.ui.formatters.events.run_success import RunSuccessFormatter
from worktree.core.db import RunStatus

FIRST_COMPLETED = FormatterCase(
    data=RunSuccessEvent(session_id="sess_123", blueprint_name="my_blueprint", status=RunStatus.COMPLETED),
    view=RunSuccessEvent(session_id="sess_123", blueprint_name="my_blueprint", status=RunStatus.COMPLETED),
    render_expectations=["my_blueprint", "sess_123", "completed"],
)

SECOND_COMPLETED = FormatterCase(
    data=RunSuccessEvent(session_id="sess_456", blueprint_name="deploy-flow", status=RunStatus.COMPLETED),
    view=RunSuccessEvent(session_id="sess_456", blueprint_name="deploy-flow", status=RunStatus.COMPLETED),
    render_expectations=["deploy-flow", "sess_456", "completed"],
)

RUN_SUCCESS_CASES = [
    pytest.param(FIRST_COMPLETED, id="first_completed"),
    pytest.param(SECOND_COMPLETED, id="second_completed"),
]

RUN_SUCCESS_PAYLOAD_CASES = [
    pytest.param(
        FIRST_COMPLETED,
        {
            "session_id": "sess_123",
            "blueprint_name": "my_blueprint",
            "status": "completed",
        },
        id="first_completed",
    ),
    pytest.param(
        SECOND_COMPLETED,
        {
            "session_id": "sess_456",
            "blueprint_name": "deploy-flow",
            "status": "completed",
        },
        id="second_completed",
    ),
]


class RunSuccessFormatterTests:
    @pytest.mark.parametrize("case", RUN_SUCCESS_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[RunSuccessEvent, RunSuccessEvent]) -> None:
        assert RunSuccessFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), RUN_SUCCESS_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[RunSuccessEvent, RunSuccessEvent],
        expected_payload: dict[str, Any],
    ) -> None:
        assert RunSuccessFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", RUN_SUCCESS_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[RunSuccessEvent, RunSuccessEvent]) -> None:
        rendered = render_rich(RunSuccessFormatter().to_rich(case.data))
        for expected in case.render_expectations:
            assert expected in rendered
