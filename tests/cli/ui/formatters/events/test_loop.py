"""Tier 2 presentation contract tests for LoopLifecycleFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.events import LoopLifecycleEvent
from worktree.cli.ui.formatters.events.loop import LoopLifecycleFormatter

LOOP_START = FormatterCase(
    data=LoopLifecycleEvent(
        loop_id="loop_1",
        action="start",
        turn=None,
        max_iterations=5,
        status=None,
        message=None,
    ),
    view=LoopLifecycleEvent(
        loop_id="loop_1",
        action="start",
        turn=None,
        max_iterations=5,
        status=None,
        message=None,
    ),
    render_expectations=["loop_1"],
)

TURN_START = FormatterCase(
    data=LoopLifecycleEvent(
        loop_id="loop_1",
        action="turn_start",
        turn=2,
        max_iterations=5,
        status=None,
        message=None,
    ),
    view=LoopLifecycleEvent(
        loop_id="loop_1",
        action="turn_start",
        turn=2,
        max_iterations=5,
        status=None,
        message=None,
    ),
    render_expectations=["loop_1"],
)

CONDITIONS_EVALUATED = FormatterCase(
    data=LoopLifecycleEvent(
        loop_id="loop_1",
        action="conditions_evaluated",
        turn=None,
        max_iterations=None,
        status=None,
        message="Evaluated 1 condition(s)",
    ),
    view=LoopLifecycleEvent(
        loop_id="loop_1",
        action="conditions_evaluated",
        turn=None,
        max_iterations=None,
        status=None,
        message="Evaluated 1 condition(s)",
    ),
    render_expectations=["Evaluated 1 condition(s)"],
)

LOOP_DONE = FormatterCase(
    data=LoopLifecycleEvent(
        loop_id="loop_1",
        action="done",
        turn=3,
        max_iterations=5,
        status="completed",
        message=None,
    ),
    view=LoopLifecycleEvent(
        loop_id="loop_1",
        action="done",
        turn=3,
        max_iterations=5,
        status="completed",
        message=None,
    ),
    render_expectations=["loop_1"],
)

LOOP_CASES = [
    pytest.param(LOOP_START, id="loop_start"),
    pytest.param(TURN_START, id="turn_start"),
    pytest.param(CONDITIONS_EVALUATED, id="conditions_evaluated"),
    pytest.param(LOOP_DONE, id="loop_done"),
]

LOOP_PAYLOAD_CASES = [
    pytest.param(
        LOOP_START,
        {
            "loop_id": "loop_1",
            "action": "start",
            "turn": None,
            "max_iterations": 5,
            "status": None,
            "message": None,
        },
        id="loop_start",
    ),
    pytest.param(
        TURN_START,
        {
            "loop_id": "loop_1",
            "action": "turn_start",
            "turn": 2,
            "max_iterations": 5,
            "status": None,
            "message": None,
        },
        id="turn_start",
    ),
    pytest.param(
        CONDITIONS_EVALUATED,
        {
            "loop_id": "loop_1",
            "action": "conditions_evaluated",
            "turn": None,
            "max_iterations": None,
            "status": None,
            "message": "Evaluated 1 condition(s)",
        },
        id="conditions_evaluated",
    ),
    pytest.param(
        LOOP_DONE,
        {
            "loop_id": "loop_1",
            "action": "done",
            "turn": 3,
            "max_iterations": 5,
            "status": "completed",
            "message": None,
        },
        id="loop_done",
    ),
]


class LoopLifecycleFormatterTests:
    """Tier 2 presentation contract tests for LoopLifecycleFormatter."""

    @pytest.mark.parametrize("case", LOOP_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[LoopLifecycleEvent, LoopLifecycleEvent]) -> None:
        """Verify transform derives the identity view representation."""
        assert LoopLifecycleFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), LOOP_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[LoopLifecycleEvent, LoopLifecycleEvent],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert LoopLifecycleFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", LOOP_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[LoopLifecycleEvent, LoopLifecycleEvent]
    ) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(LoopLifecycleFormatter().to_rich(case.data))
        for expected in case.render_expectations:
            assert expected in rendered
