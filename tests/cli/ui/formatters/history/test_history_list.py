"""Tier 2 presentation contract tests for HistoryListFormatter."""

from __future__ import annotations

from tests.helpers import render_rich
from worktree.cli.ui.formatters.history.history_list import HistoryListFormatter
from worktree.core.blueprint import BlueprintKind
from worktree.core.db import RunRecord, RunStatus
from worktree.core.history.models import (
    HistoryListResult,
    HistoryListStatus,
)


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

    def test_to_rich_with_runs_renders_session_and_duration(self) -> None:
        formatter = HistoryListFormatter()
        run = _sample_run_record()
        result = HistoryListResult(status=HistoryListStatus.OK, runs=[run])

        rendered = render_rich(formatter.to_rich(result))
        assert "sess-12345678" in rendered
        assert "deploy-task" in rendered
        assert "10.00s" in rendered

    def test_to_rich_when_empty_renders_no_runs(self) -> None:
        formatter = HistoryListFormatter()
        result = HistoryListResult(status=HistoryListStatus.OK, runs=[])

        rendered = render_rich(formatter.to_rich(result))
        assert "sess-" not in rendered

    def test_to_rich_with_warnings_renders_warning_and_run(self) -> None:
        formatter = HistoryListFormatter()
        run = _sample_run_record()
        result = HistoryListResult(
            status=HistoryListStatus.OK,
            runs=[run],
            warnings=["Reconciled 1 interrupted session (session_id: sess-stale)."],
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "Reconciled 1 interrupted session" in rendered
        assert "sess-12345678" in rendered

    def test_to_rich_when_errors_renders_error_message(self) -> None:
        formatter = HistoryListFormatter()
        result = HistoryListResult(
            status=HistoryListStatus.OK,
            errors=["Database query failed."],
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "Database query failed." in rendered

    def test_to_json_serializable_returns_exact_dict(self) -> None:
        formatter = HistoryListFormatter()
        run = _sample_run_record()
        result = HistoryListResult(
            status=HistoryListStatus.OK,
            runs=[run],
            warnings=["Warning test"],
        )

        dumped = formatter.to_json_serializable(result)
        assert dumped == {
            "status": "ok",
            "runs": [
                {
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
                }
            ],
            "warnings": ["Warning test"],
            "errors": [],
            "fixes": [],
        }
