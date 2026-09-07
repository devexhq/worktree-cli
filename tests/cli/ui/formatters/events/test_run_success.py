"""Tier 2 presentation contract tests for RunSuccessFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.events import RunSuccessEvent
from worktree.cli.ui.formatters.events.run_success import RunSuccessFormatter
from worktree.core.db import BlueprintKind, RunStatus

TASK_COMPLETED = FormatterCase(
    data=RunSuccessEvent(
        session_id="sess_123",
        blueprint_name="my_task",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
    ),
    view=RunSuccessEvent(
        session_id="sess_123",
        blueprint_name="my_task",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
    ),
    render_expectations=["my_task", "sess_123", "completed"],
)

WORKFLOW_COMPLETED = FormatterCase(
    data=RunSuccessEvent(
        session_id="sess_456",
        blueprint_name="deploy-flow",
        kind=BlueprintKind.WORKFLOW,
        status=RunStatus.COMPLETED,
    ),
    view=RunSuccessEvent(
        session_id="sess_456",
        blueprint_name="deploy-flow",
        kind=BlueprintKind.WORKFLOW,
        status=RunStatus.COMPLETED,
    ),
    render_expectations=["deploy-flow", "sess_456", "completed"],
)

RUN_SUCCESS_CASES = [
    pytest.param(TASK_COMPLETED, id="task_completed"),
    pytest.param(WORKFLOW_COMPLETED, id="workflow_completed"),
]

RUN_SUCCESS_PAYLOAD_CASES = [
    pytest.param(
        TASK_COMPLETED,
        {
            "session_id": "sess_123",
            "blueprint_name": "my_task",
            "kind": "task",
            "status": "completed",
        },
        id="task_completed",
    ),
    pytest.param(
        WORKFLOW_COMPLETED,
        {
            "session_id": "sess_456",
            "blueprint_name": "deploy-flow",
            "kind": "workflow",
            "status": "completed",
        },
        id="workflow_completed",
    ),
]


class RunSuccessFormatterTests:
    """Tier 2 presentation contract tests for RunSuccessFormatter."""

    @pytest.mark.parametrize("case", RUN_SUCCESS_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[RunSuccessEvent, RunSuccessEvent]) -> None:
        """Verify transform derives the identity view representation."""
        assert RunSuccessFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), RUN_SUCCESS_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[RunSuccessEvent, RunSuccessEvent],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert RunSuccessFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", RUN_SUCCESS_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[RunSuccessEvent, RunSuccessEvent]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(RunSuccessFormatter().to_rich(case.data))
        for expected in case.render_expectations:
            assert expected in rendered
