"""Tier 2 presentation contract tests for HistoryShowFormatter."""

from __future__ import annotations

import json

from tests.helpers import render_rich
from worktree.cli.ui.formatters.history.history_show import HistoryShowFormatter
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
        branch_name=branch_name,
        started_at=started_at,
        completed_at=completed_at,
        error_message=error_message,
        checkpoint_json=checkpoint_json,
    )


class HistoryShowFormatterTests:
    """Tests for HistoryShowFormatter."""

    def test_to_rich_completed_run_renders_metadata(self) -> None:
        formatter = HistoryShowFormatter()
        run = _sample_run_record()
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "sess-12345678" in rendered
        assert "deploy-task" in rendered
        assert "feature/test" in rendered
        assert "10.00s" in rendered

    def test_to_rich_with_error_message_renders_error_message(self) -> None:
        formatter = HistoryShowFormatter()
        run = _sample_run_record(
            status=RunStatus.FAILED,
            error_message="Step 'checkout' failed with exit code 1.",
        )
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "sess-12345678" in rendered
        assert "Step 'checkout' failed with exit code 1." in rendered

    def test_to_rich_with_checkpoint_renders_diagnostic_and_step(self) -> None:
        formatter = HistoryShowFormatter()
        step_result = StepResult(
            step_id="step-1",
            status="completed",
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_seconds=1.23,
        )
        checkpoint = RunCheckpoint(
            next_step_index=1,
            pending_step_id="step-2",
            diagnostic="Waiting for approval",
            step_results=[step_result],
        )
        run = _sample_run_record(
            status=RunStatus.PAUSED,
            checkpoint_json=checkpoint.model_dump_json(),
        )
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "step-2" in rendered
        assert "Waiting for approval" in rendered
        assert "step-1" in rendered

    def test_to_rich_raw_checkpoint_json_fallback_renders_custom_field(self) -> None:
        formatter = HistoryShowFormatter()
        raw_json = json.dumps({"custom_field": "custom_val"})
        run = _sample_run_record(checkpoint_json=raw_json)
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "custom_field" in rendered

    def test_to_rich_when_not_found_renders_session_id(self) -> None:
        formatter = HistoryShowFormatter()
        result = HistoryShowResult(
            status=HistoryShowStatus.NOT_FOUND,
            session_id="nonexistent-sess",
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "nonexistent-sess" in rendered

    def test_to_rich_when_errors_renders_error_message(self) -> None:
        formatter = HistoryShowFormatter()
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-1",
            errors=["Database locked"],
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "Database locked" in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = HistoryShowFormatter()
        run = _sample_run_record()
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "ok",
            "session_id": "sess-12345678",
            "run": {
                "id": 1,
                "session_id": "sess-12345678",
                "blueprint_name": "deploy-task",
                "kind": "task",
                "branch_name": "feature/test",
                "status": "completed",
                "started_at": "2026-08-19 01:00:00",
                "completed_at": "2026-08-19 01:00:10",
                "error_message": None,
                "checkpoint_json": None,
                "pid": None,
            },
            "errors": [],
            "warnings": [],
            "fixes": [],
        }
