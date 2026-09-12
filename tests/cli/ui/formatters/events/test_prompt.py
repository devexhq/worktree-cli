"""Tier 2 presentation contract tests for PromptFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.events import PromptEvent, PromptOption
from worktree.cli.ui.formatters.events.prompt import PromptFormatter

_CONTINUE_OPTION = PromptOption(key="c", label="Continue", decision="continue")
_ABORT_OPTION = PromptOption(key="a", label="Abort", decision="abort")

WITH_DIAGNOSTIC = FormatterCase(
    data=PromptEvent(
        prompt_type="step_failure",
        prompt_id="step-1",
        title="Action Needed",
        diagnostic="Step timed out",
        options=[_CONTINUE_OPTION],
        default="c",
    ),
    view=PromptEvent(
        prompt_type="step_failure",
        prompt_id="step-1",
        title="Action Needed",
        diagnostic="Step timed out",
        options=[_CONTINUE_OPTION],
        default="c",
    ),
    render_expectations=["Action Needed", "Step timed out"],
)

WITHOUT_DIAGNOSTIC = FormatterCase(
    data=PromptEvent(
        prompt_type="step_failure",
        prompt_id="step-2",
        title="Blueprint Prompt",
        diagnostic=None,
        options=[_ABORT_OPTION],
    ),
    view=PromptEvent(
        prompt_type="step_failure",
        prompt_id="step-2",
        title="Blueprint Prompt",
        diagnostic=None,
        options=[_ABORT_OPTION],
    ),
    render_expectations=["Blueprint Prompt"],
)

PROMPT_CASES = [
    pytest.param(WITH_DIAGNOSTIC, id="with_diagnostic"),
    pytest.param(WITHOUT_DIAGNOSTIC, id="without_diagnostic"),
]

PROMPT_PAYLOAD_CASES = [
    pytest.param(
        WITH_DIAGNOSTIC,
        {
            "prompt_type": "step_failure",
            "prompt_id": "step-1",
            "title": "Action Needed",
            "diagnostic": "Step timed out",
            "options": [{"key": "c", "label": "Continue", "decision": "continue"}],
            "default": "c",
        },
        id="with_diagnostic",
    ),
    pytest.param(
        WITHOUT_DIAGNOSTIC,
        {
            "prompt_type": "step_failure",
            "prompt_id": "step-2",
            "title": "Blueprint Prompt",
            "diagnostic": None,
            "options": [{"key": "a", "label": "Abort", "decision": "abort"}],
            "default": "abort",
        },
        id="without_diagnostic",
    ),
]


class PromptFormatterTests:
    @pytest.mark.parametrize("case", PROMPT_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[PromptEvent, PromptEvent]) -> None:
        assert PromptFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), PROMPT_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[PromptEvent, PromptEvent],
        expected_payload: dict[str, Any],
    ) -> None:
        assert PromptFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", PROMPT_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[PromptEvent, PromptEvent]) -> None:
        rendered = render_rich(PromptFormatter().to_rich(case.data))
        view = case.view

        for expected in case.render_expectations:
            assert expected in rendered

        for opt in view.options:
            assert opt.key in rendered
            assert opt.label in rendered
