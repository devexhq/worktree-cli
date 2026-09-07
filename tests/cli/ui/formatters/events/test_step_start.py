"""Tier 2 presentation contract tests for StepStartFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.events import StepStartEvent
from worktree.cli.ui.formatters.events.step_start import StepStartFormatter

WITH_NAME_AND_COMMAND = FormatterCase(
    data=StepStartEvent(
        idx=1,
        total=3,
        step_id="step-1",
        name="Run Tests",
        command="pytest",
    ),
    view=StepStartEvent(
        idx=1,
        total=3,
        step_id="step-1",
        name="Run Tests",
        command="pytest",
    ),
    render_expectations=["1", "3", "Run Tests", "pytest"],
)

WITHOUT_NAME_AND_COMMAND = FormatterCase(
    data=StepStartEvent(
        idx=2,
        total=3,
        step_id="step-2",
        name=None,
        command=None,
    ),
    view=StepStartEvent(
        idx=2,
        total=3,
        step_id="step-2",
        name=None,
        command=None,
    ),
    render_expectations=["2", "3", "step-2"],
)

STEP_START_CASES = [
    pytest.param(WITH_NAME_AND_COMMAND, id="with_name_and_command"),
    pytest.param(WITHOUT_NAME_AND_COMMAND, id="without_name_and_command"),
]

STEP_START_PAYLOAD_CASES = [
    pytest.param(
        WITH_NAME_AND_COMMAND,
        {
            "idx": 1,
            "total": 3,
            "step_id": "step-1",
            "name": "Run Tests",
            "command": "pytest",
        },
        id="with_name_and_command",
    ),
    pytest.param(
        WITHOUT_NAME_AND_COMMAND,
        {
            "idx": 2,
            "total": 3,
            "step_id": "step-2",
            "name": None,
            "command": None,
        },
        id="without_name_and_command",
    ),
]


class StepStartFormatterTests:
    """Tier 2 presentation contract tests for StepStartFormatter."""

    @pytest.mark.parametrize("case", STEP_START_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[StepStartEvent, StepStartEvent]) -> None:
        """Verify transform derives the identity view representation."""
        assert StepStartFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), STEP_START_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[StepStartEvent, StepStartEvent],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert StepStartFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", STEP_START_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[StepStartEvent, StepStartEvent]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(StepStartFormatter().to_rich(case.data))
        for expected in case.render_expectations:
            assert expected in rendered
