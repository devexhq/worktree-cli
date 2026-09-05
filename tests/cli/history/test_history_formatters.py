"""Unit tests for history ComponentFormatters and UI dispatching."""

from __future__ import annotations

import json

import pytest
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tests.helpers import make_dispatcher_with_buffer, render_rich
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.formatters.history import (
    HistoryListFormatter,
    HistoryShowFormatter,
    register_history_formatters,
)
from worktree.core.blueprint import BlueprintKind
from worktree.core.db import RunRecord, RunStatus
from worktree.core.history.models import (
    HistoryListResult,
    HistoryListStatus,
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


class HistoryListFormatterTests:
    """Tests for HistoryListFormatter."""

    def test_to_rich_with_runs(self) -> None:
        formatter = HistoryListFormatter()
        run = _sample_run_record()
        result = HistoryListResult(status=HistoryListStatus.OK, runs=[run])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Table)
        rendered = render_rich(rich_renderable)
        assert "Execution History" in rendered
        assert "sess-12345678" in rendered
        assert "deploy-task" in rendered
        assert "10.00s" in rendered

    def test_to_rich_empty(self) -> None:
        formatter = HistoryListFormatter()
        result = HistoryListResult(status=HistoryListStatus.OK, runs=[])

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Text)
        assert "No execution history found." in rich_renderable.plain

    def test_to_rich_with_warnings(self) -> None:
        formatter = HistoryListFormatter()
        run = _sample_run_record()
        result = HistoryListResult(
            status=HistoryListStatus.OK,
            runs=[run],
            warnings=["Reconciled 1 interrupted session (session_id: sess-stale)."],
        )

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Group)
        rendered = render_rich(rich_renderable)
        assert "Reconciled 1 interrupted session" in rendered
        assert "sess-12345678" in rendered

    def test_to_rich_errors(self) -> None:
        formatter = HistoryListFormatter()
        result = HistoryListResult(
            status=HistoryListStatus.OK,
            errors=["Database query failed."],
        )

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "History List Failed" in rendered
        assert "Database query failed." in rendered

    def test_to_json_serializable(self) -> None:
        formatter = HistoryListFormatter()
        run = _sample_run_record()
        result = HistoryListResult(
            status=HistoryListStatus.OK,
            runs=[run],
            warnings=["Warning test"],
        )

        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert dumped["status"] == "ok"
        assert len(dumped["runs"]) == 1
        assert dumped["runs"][0]["session_id"] == "sess-12345678"
        assert dumped["warnings"] == ["Warning test"]
        assert dumped["errors"] == []


class HistoryShowFormatterTests:
    """Tests for HistoryShowFormatter."""

    def test_to_rich_success(self) -> None:
        formatter = HistoryShowFormatter()
        run = _sample_run_record()
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Session Metadata: sess-12345678" in rendered
        assert "deploy-task" in rendered
        assert "feature/test" in rendered
        assert "10.00s" in rendered

    def test_to_rich_with_error_message(self) -> None:
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

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Group)
        rendered = render_rich(rich_renderable)
        assert "Session Metadata: sess-12345678" in rendered
        assert "Error Details" in rendered
        assert "Step 'checkout' failed with exit code 1." in rendered

    def test_to_rich_with_checkpoint(self) -> None:
        formatter = HistoryShowFormatter()
        step_res = StepResult(
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
            step_results=[step_res],
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

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Group)
        rendered = render_rich(rich_renderable)
        assert "Checkpoint Details" in rendered
        assert "Pending Step ID:" in rendered
        assert "step-2" in rendered
        assert "Waiting for approval" in rendered
        assert "Step Results" in rendered
        assert "step-1" in rendered

    def test_to_rich_raw_checkpoint_json_fallback(self) -> None:
        formatter = HistoryShowFormatter()
        raw_json = json.dumps({"custom_field": "custom_val"})
        run = _sample_run_record(checkpoint_json=raw_json)
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Group)
        rendered = render_rich(rich_renderable)
        assert "Checkpoint JSON" in rendered
        assert "custom_field" in rendered

    def test_to_rich_not_found(self) -> None:
        formatter = HistoryShowFormatter()
        result = HistoryShowResult(
            status=HistoryShowStatus.NOT_FOUND,
            session_id="nonexistent-sess",
        )

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Session Not Found" in rendered
        assert "Session 'nonexistent-sess' not found." in rendered

    def test_to_rich_errors(self) -> None:
        formatter = HistoryShowFormatter()
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-1",
            errors=["Database locked"],
        )

        rich_renderable = formatter.to_rich(result)
        assert isinstance(rich_renderable, Panel)
        rendered = render_rich(rich_renderable)
        assert "Session Show Failed" in rendered
        assert "Database locked" in rendered

    def test_to_json_serializable(self) -> None:
        formatter = HistoryShowFormatter()
        run = _sample_run_record()
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        dumped = formatter.to_json_serializable(result)
        assert isinstance(dumped, dict)
        assert dumped["status"] == "ok"
        assert dumped["session_id"] == "sess-12345678"
        assert dumped["run"]["blueprint_name"] == "deploy-task"
        assert dumped["errors"] == []


class HistoryDispatcherIntegrationTests:
    """Integration tests for UiDispatcher history formatters and JSON/terminal output."""

    def test_register_history_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_history_formatters(dispatcher)

        assert HistoryListResult in dispatcher._registry
        assert HistoryShowResult in dispatcher._registry
        assert isinstance(dispatcher._registry[HistoryListResult], HistoryListFormatter)
        assert isinstance(dispatcher._registry[HistoryShowResult], HistoryShowFormatter)

    def test_ui_dispatcher_default_registrations(self) -> None:
        assert HistoryListResult in ui_dispatcher._registry
        assert HistoryShowResult in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[HistoryListResult], HistoryListFormatter)
        assert isinstance(ui_dispatcher._registry[HistoryShowResult], HistoryShowFormatter)

    def test_dispatcher_list_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_history_formatters(dispatcher)
        run = _sample_run_record()
        result = HistoryListResult(status=HistoryListStatus.OK, runs=[run])

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "HistoryListResult"
        assert payload["payload"]["status"] == "ok"
        assert len(payload["payload"]["runs"]) == 1
        assert payload["payload"]["runs"][0]["session_id"] == "sess-12345678"

    def test_dispatcher_show_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_history_formatters(dispatcher)
        run = _sample_run_record()
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "HistoryShowResult"
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["session_id"] == "sess-12345678"
        assert payload["payload"]["run"]["session_id"] == "sess-12345678"

    def test_dispatcher_terminal_format(self) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        run = _sample_run_record()
        result = HistoryListResult(status=HistoryListStatus.OK, runs=[run])

        dispatcher.dispatch(result, output_format="terminal")

        output = buffer.getvalue()
        assert "Execution History" in output
        assert "sess-12345678" in output
