"""Tier 2 presentation contract tests for MessageFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.events import MessageEvent
from worktree.cli.ui.formatters.events.message import MessageFormatter

STYLED_MESSAGE = FormatterCase(
    data=MessageEvent(message="Operation finished", style="bold"),
    view=MessageEvent(message="Operation finished", style="bold"),
    render_expectations=["Operation finished"],
)

PLAIN_MESSAGE = FormatterCase(
    data=MessageEvent(message="Running task 'build'...", style=None),
    view=MessageEvent(message="Running task 'build'...", style=None),
    render_expectations=["Running task 'build'..."],
)

MESSAGE_CASES = [
    pytest.param(STYLED_MESSAGE, id="styled_message"),
    pytest.param(PLAIN_MESSAGE, id="plain_message"),
]

MESSAGE_PAYLOAD_CASES = [
    pytest.param(
        STYLED_MESSAGE,
        {
            "message": "Operation finished",
            "style": "bold",
        },
        id="styled_message",
    ),
    pytest.param(
        PLAIN_MESSAGE,
        {
            "message": "Running task 'build'...",
            "style": None,
        },
        id="plain_message",
    ),
]


class MessageFormatterTests:
    """Tier 2 presentation contract tests for MessageFormatter."""

    @pytest.mark.parametrize("case", MESSAGE_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[MessageEvent, MessageEvent]) -> None:
        """Verify transform derives the identity view representation."""
        assert MessageFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), MESSAGE_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[MessageEvent, MessageEvent],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert MessageFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", MESSAGE_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[MessageEvent, MessageEvent]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(MessageFormatter().to_rich(case.data))
        for expected in case.render_expectations:
            assert expected in rendered
