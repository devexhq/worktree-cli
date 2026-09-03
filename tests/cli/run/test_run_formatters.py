"""Tests for BlueprintRunFormatter and UiDispatcher integration."""

from __future__ import annotations

import io

from rich.console import Console

from worktree.cli.run.formatters import BlueprintRunFormatter
from worktree.cli.ui.dispatcher import UiDispatcher
from worktree.core.blueprint.models import BlueprintKind, BlueprintRunResult
from worktree.core.db import RunRecord, RunStatus


def test_blueprint_run_formatter_empty() -> None:
    formatter = BlueprintRunFormatter()
    outcome = BlueprintRunResult()
    rendered = formatter.to_rich(outcome)
    assert rendered.plain == ""


def test_blueprint_run_formatter_errors_only() -> None:
    formatter = BlueprintRunFormatter()
    outcome = BlueprintRunResult(errors=["Failed to load blueprint."])
    rendered = formatter.to_rich(outcome)
    buf = io.StringIO()
    Console(file=buf, force_terminal=False).print(rendered)
    assert "Failed to load blueprint." in buf.getvalue()


def test_blueprint_run_formatter_output_items() -> None:
    formatter = BlueprintRunFormatter()
    outcome = BlueprintRunResult(
        run_record=RunRecord(
            id=1,
            session_id="session_123",
            blueprint_name="my_task",
            kind=BlueprintKind.TASK,
            branch_name="main",
            status=RunStatus.COMPLETED,
            started_at="2026-09-02T00:00:00Z",
        ),
        output_items=["Executing step...", "Done!"],
    )
    rendered = formatter.to_rich(outcome)
    buf = io.StringIO()
    Console(file=buf, force_terminal=False).print(rendered)
    assert "Executing step..." in buf.getvalue()
    assert "Done!" in buf.getvalue()


def test_blueprint_run_formatter_to_json_serializable() -> None:
    formatter = BlueprintRunFormatter()
    record = RunRecord(
        id=1,
        session_id="session_123",
        blueprint_name="my_task",
        kind=BlueprintKind.TASK,
        branch_name="main",
        status=RunStatus.COMPLETED,
        started_at="2026-09-02T00:00:00Z",
    )
    outcome = BlueprintRunResult(
        run_record=record,
        output_items=["Line 1", "Line 2"],
    )
    data = formatter.to_json_serializable(outcome)
    assert data["ok"] is True
    assert data["run_record"]["session_id"] == "session_123"
    assert data["output_items"] == ["Line 1", "Line 2"]


def test_blueprint_run_dispatcher_terminal() -> None:
    string_io = io.StringIO()
    console = Console(file=string_io, force_terminal=False)
    dispatcher = UiDispatcher(console=console)
    dispatcher.register(BlueprintRunResult, BlueprintRunFormatter())

    outcome = BlueprintRunResult(
        output_items=["Task finished successfully."],
    )
    dispatcher.dispatch(outcome, output_format="terminal")
    assert "Task finished successfully." in string_io.getvalue()
