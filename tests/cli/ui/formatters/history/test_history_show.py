"""Tier 2 presentation contract tests for HistoryShowFormatter."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.history.common import format_run_duration
from worktree.cli.ui.formatters.history.history_show import HistoryShowFormatter
from worktree.cli.ui.formatters.history.history_views import (
    CheckpointDetailsView,
    CheckpointStepView,
    HistoryShowView,
    RunSummaryView,
)
from worktree.core.blueprint import BlueprintKind
from worktree.core.db import RunRecord, RunStatus
from worktree.core.history.models import (
    HistoryShowResult,
    HistoryShowStatus,
)
from worktree.core.runtime import RunCheckpoint
from worktree.core.step import StepResult


def _sample_run_record(
    *,
    session_id: str = "sess-12345678",
    blueprint_name: str = "deploy-task",
    kind: BlueprintKind = BlueprintKind.TASK,
    status: RunStatus = RunStatus.COMPLETED,
    branch_name: str | None = "feature/test",
    started_at: str | None = "2026-08-19 01:00:00",
    completed_at: str | None = "2026-08-19 01:00:10",
    error_message: str | None = None,
    checkpoint_json: str | None = None,
) -> RunRecord:
    return RunRecord(
        id=1,
        session_id=session_id,
        blueprint_name=blueprint_name,
        kind=kind,
        status=status,
        branch_name=branch_name or "",
        started_at=started_at,
        completed_at=completed_at,
        error_message=error_message,
        checkpoint_json=checkpoint_json,
    )


def _make_run_summary_view(**overrides: Any) -> RunSummaryView:
    defaults: dict[str, Any] = {
        "session_id": "sess-12345678",
        "kind": "task",
        "blueprint_name": "deploy-task",
        "status": "completed",
        "branch_name": "feature/test",
        "started_at": "2026-08-19 01:00:00",
        "completed_at": "2026-08-19 01:00:10",
        "duration_seconds": 10.0,
        "error_message": None,
    }
    defaults.update(overrides)
    return RunSummaryView(**defaults)


def _make_history_show_view(**overrides: Any) -> HistoryShowView:
    defaults: dict[str, Any] = {
        "status": HistoryShowStatus.OK,
        "session_id": "sess-12345678",
        "run": _make_run_summary_view(),
        "checkpoint": None,
        "checkpoint_raw": None,
        "errors": [],
        "warnings": [],
        "fixes": [],
    }
    defaults.update(overrides)
    return HistoryShowView(**defaults)


COMPLETED_RUN = FormatterCase(
    data=HistoryShowResult(
        status=HistoryShowStatus.OK,
        session_id="sess-12345678",
        run=_sample_run_record(),
    ),
    view=_make_history_show_view(),
)

FAILED_RUN_WITH_ERROR = FormatterCase(
    data=HistoryShowResult(
        status=HistoryShowStatus.OK,
        session_id="sess-12345678",
        run=_sample_run_record(
            status=RunStatus.FAILED,
            error_message="Step 'checkout' failed with exit code 1.",
        ),
    ),
    view=_make_history_show_view(
        run=_make_run_summary_view(
            status="failed",
            error_message="Step 'checkout' failed with exit code 1.",
        )
    ),
)

_STEP_RESULT = StepResult(
    step_id="step-1",
    status="completed",
    exit_code=0,
    stdout="ok",
    stderr="",
    duration_seconds=1.23,
)
_CHECKPOINT = RunCheckpoint(
    next_step_index=1,
    pending_step_id="step-2",
    diagnostic="Waiting for approval",
    step_results=[_STEP_RESULT],
)

PAUSED_RUN_WITH_CHECKPOINT = FormatterCase(
    data=HistoryShowResult(
        status=HistoryShowStatus.OK,
        session_id="sess-12345678",
        run=_sample_run_record(
            status=RunStatus.PAUSED,
            completed_at=None,
            checkpoint_json=_CHECKPOINT.model_dump_json(),
        ),
    ),
    view=_make_history_show_view(
        run=_make_run_summary_view(
            status="paused",
            completed_at=None,
            duration_seconds=None,
        ),
        checkpoint=CheckpointDetailsView(
            pending_step_id="step-2",
            next_step_index=1,
            diagnostic="Waiting for approval",
            step_results=[
                CheckpointStepView(
                    step_id="step-1",
                    status="completed",
                    duration_seconds=1.23,
                    error_message=None,
                )
            ],
        ),
    ),
)

_RAW_JSON = json.dumps({"custom_field": "custom_val"})
RUN_WITH_RAW_CHECKPOINT_FALLBACK = FormatterCase(
    data=HistoryShowResult(
        status=HistoryShowStatus.OK,
        session_id="sess-12345678",
        run=_sample_run_record(checkpoint_json=_RAW_JSON),
    ),
    view=_make_history_show_view(checkpoint_raw=_RAW_JSON),
)

NOT_FOUND = FormatterCase(
    data=HistoryShowResult(
        status=HistoryShowStatus.NOT_FOUND,
        session_id="nonexistent-sess",
    ),
    view=_make_history_show_view(
        status=HistoryShowStatus.NOT_FOUND,
        session_id="nonexistent-sess",
        run=None,
    ),
)

SHOW_ERROR = FormatterCase(
    data=HistoryShowResult(
        status=HistoryShowStatus.OK,
        session_id="sess-1",
        errors=["Database locked"],
    ),
    view=_make_history_show_view(
        session_id="sess-1",
        run=None,
        errors=["Database locked"],
    ),
)

HISTORY_SHOW_CASES = [
    pytest.param(COMPLETED_RUN, id="completed_run"),
    pytest.param(FAILED_RUN_WITH_ERROR, id="failed_run_with_error"),
    pytest.param(PAUSED_RUN_WITH_CHECKPOINT, id="paused_run_with_checkpoint"),
    pytest.param(RUN_WITH_RAW_CHECKPOINT_FALLBACK, id="raw_checkpoint_fallback"),
    pytest.param(NOT_FOUND, id="not_found"),
    pytest.param(SHOW_ERROR, id="show_error"),
]

HISTORY_SHOW_PAYLOAD_CASES = [
    pytest.param(
        COMPLETED_RUN,
        {
            "status": "ok",
            "session_id": "sess-12345678",
            "run": {
                "session_id": "sess-12345678",
                "kind": "task",
                "blueprint_name": "deploy-task",
                "status": "completed",
                "branch_name": "feature/test",
                "started_at": "2026-08-19 01:00:00",
                "completed_at": "2026-08-19 01:00:10",
                "duration_seconds": 10.0,
                "error_message": None,
            },
            "checkpoint": None,
            "checkpoint_raw": None,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="completed_run",
    ),
    pytest.param(
        FAILED_RUN_WITH_ERROR,
        {
            "status": "ok",
            "session_id": "sess-12345678",
            "run": {
                "session_id": "sess-12345678",
                "kind": "task",
                "blueprint_name": "deploy-task",
                "status": "failed",
                "branch_name": "feature/test",
                "started_at": "2026-08-19 01:00:00",
                "completed_at": "2026-08-19 01:00:10",
                "duration_seconds": 10.0,
                "error_message": "Step 'checkout' failed with exit code 1.",
            },
            "checkpoint": None,
            "checkpoint_raw": None,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="failed_run_with_error",
    ),
    pytest.param(
        PAUSED_RUN_WITH_CHECKPOINT,
        {
            "status": "ok",
            "session_id": "sess-12345678",
            "run": {
                "session_id": "sess-12345678",
                "kind": "task",
                "blueprint_name": "deploy-task",
                "status": "paused",
                "branch_name": "feature/test",
                "started_at": "2026-08-19 01:00:00",
                "completed_at": None,
                "duration_seconds": None,
                "error_message": None,
            },
            "checkpoint": {
                "pending_step_id": "step-2",
                "next_step_index": 1,
                "diagnostic": "Waiting for approval",
                "step_results": [
                    {
                        "step_id": "step-1",
                        "status": "completed",
                        "duration_seconds": 1.23,
                        "error_message": None,
                    }
                ],
            },
            "checkpoint_raw": None,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="paused_run_with_checkpoint",
    ),
    pytest.param(
        RUN_WITH_RAW_CHECKPOINT_FALLBACK,
        {
            "status": "ok",
            "session_id": "sess-12345678",
            "run": {
                "session_id": "sess-12345678",
                "kind": "task",
                "blueprint_name": "deploy-task",
                "status": "completed",
                "branch_name": "feature/test",
                "started_at": "2026-08-19 01:00:00",
                "completed_at": "2026-08-19 01:00:10",
                "duration_seconds": 10.0,
                "error_message": None,
            },
            "checkpoint": None,
            "checkpoint_raw": _RAW_JSON,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="raw_checkpoint_fallback",
    ),
    pytest.param(
        NOT_FOUND,
        {
            "status": "not_found",
            "session_id": "nonexistent-sess",
            "run": None,
            "checkpoint": None,
            "checkpoint_raw": None,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="not_found",
    ),
    pytest.param(
        SHOW_ERROR,
        {
            "status": "ok",
            "session_id": "sess-1",
            "run": None,
            "checkpoint": None,
            "checkpoint_raw": None,
            "errors": ["Database locked"],
            "warnings": [],
            "fixes": [],
        },
        id="show_error",
    ),
]


class HistoryShowFormatterTests:
    """Tier 2 presentation contract tests for HistoryShowFormatter."""

    @pytest.mark.parametrize("case", HISTORY_SHOW_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[HistoryShowResult, HistoryShowView]) -> None:
        """Verify transform derives the exact HistoryShowView model representation."""
        assert HistoryShowFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), HISTORY_SHOW_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[HistoryShowResult, HistoryShowView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert HistoryShowFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", HISTORY_SHOW_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[HistoryShowResult, HistoryShowView]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(HistoryShowFormatter().to_rich(case.data))
        view = case.view

        if view.run is not None:
            assert view.run.session_id in rendered
            assert view.run.blueprint_name in rendered
            if view.run.branch_name is not None:
                assert view.run.branch_name in rendered
            if view.run.duration_seconds is not None:
                assert format_run_duration(view.run.duration_seconds) in rendered
            if view.run.error_message is not None:
                assert view.run.error_message in rendered

        if view.checkpoint is not None:
            assert view.checkpoint.pending_step_id in rendered
            if view.checkpoint.diagnostic is not None:
                assert view.checkpoint.diagnostic in rendered
            for step in view.checkpoint.step_results:
                assert step.step_id in rendered

        if view.checkpoint_raw is not None:
            assert "custom_field" in rendered

        if view.status == HistoryShowStatus.NOT_FOUND:
            if view.session_id is not None:
                assert view.session_id in rendered

        for error in view.errors:
            assert error in rendered
