"""Single-tier CLI integration tests for wt history / wt history list."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from worktree.cli import app
from worktree.core.db import RunStatus, WorktreeDb


class HistoryListCliIntegrationTests:
    """Typer runner integration tests for wt history / wt history list."""

    def test_history_cli_bare_lists_recent_runs_exits_zero(
        self, cli_runner: CliRunner, history_workspace: Path
    ) -> None:
        """wt history: bare invocation lists seeded COMPLETED and FAILED runs, exit 0, both session IDs in stdout."""
        db = WorktreeDb(path=history_workspace)
        db.runs.create(
            session_id="session-completed", blueprint_name="task-a", blueprint_key="task-a", status=RunStatus.COMPLETED
        )
        db.runs.create(
            session_id="session-failed", blueprint_name="task-b", blueprint_key="task-b", status=RunStatus.FAILED
        )

        result = cli_runner.invoke(app, ["-p", str(history_workspace), "history"])

        assert result.exit_code == 0
        assert "session-completed" in result.stdout
        assert "session-failed" in result.stdout

    def test_history_list_cli_json_emits_literal_wire_payload(
        self, cli_runner: CliRunner, history_workspace: Path
    ) -> None:
        """wt history list --format json: stdout equals the literal HistoryListResult envelope for the two seeded runs."""
        db = WorktreeDb(path=history_workspace)
        db.runs.create(
            session_id="session-completed", blueprint_name="task-a", blueprint_key="task-a", status=RunStatus.COMPLETED
        )
        db.runs.create(
            session_id="session-failed", blueprint_name="task-b", blueprint_key="task-b", status=RunStatus.FAILED
        )

        result = cli_runner.invoke(app, ["-p", str(history_workspace), "history", "list", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["event_type"] == "HistoryListResult"
        payload = data["payload"]
        runs = payload["runs"]
        assert len(runs) == 2
        for r in runs:
            assert isinstance(r["started_at"], str)
            r["started_at"] = "<timestamp>"
        assert payload == {
            "status": "ok",
            "runs": [
                {
                    "session_id": "session-failed",
                    "blueprint_name": "task-b",
                    "status": "failed",
                    "branch_name": None,
                    "started_at": "<timestamp>",
                    "completed_at": None,
                    "duration_seconds": None,
                    "error_message": None,
                },
                {
                    "session_id": "session-completed",
                    "blueprint_name": "task-a",
                    "status": "completed",
                    "branch_name": None,
                    "started_at": "<timestamp>",
                    "completed_at": None,
                    "duration_seconds": None,
                    "error_message": None,
                },
            ],
            "total_runs": 2,
            "errors": [],
            "warnings": [],
            "fixes": [],
        }
