"""Single-tier CLI integration tests for wt history show."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tests.harness.matchers import ANY_TIMESTAMP
from worktree.cli import app
from worktree.core.db import RunStatus, WorktreeDb


class HistoryShowCliIntegrationTests:
    """Typer runner integration tests for wt history show."""

    def test_history_show_cli_known_session_exits_zero(self, cli_runner: CliRunner, history_workspace: Path) -> None:
        """wt history show <session_id>: known session, exit 0, session ID and blueprint name in stdout."""
        db = WorktreeDb(path=history_workspace)
        db.runs.create(
            session_id="session-known", blueprint_name="task-a", blueprint_key="task-a", status=RunStatus.COMPLETED
        )

        result = cli_runner.invoke(app, ["-p", str(history_workspace), "history", "show", "session-known"])

        assert result.exit_code == 0
        assert "session-known" in result.stdout
        assert "task-a" in result.stdout

    def test_history_show_cli_unknown_session_exits_one(self, cli_runner: CliRunner, history_workspace: Path) -> None:
        """wt history show <unknown-id>: exit 1, 'not found' in stdout."""
        result = cli_runner.invoke(app, ["-p", str(history_workspace), "history", "show", "missing-id"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_history_show_cli_json_emits_literal_wire_payload(
        self, cli_runner: CliRunner, history_workspace: Path
    ) -> None:
        """wt history show <session_id> --format json: stdout equals the literal HistoryShowResult envelope."""
        db = WorktreeDb(path=history_workspace)
        db.runs.create(
            session_id="session-known", blueprint_name="task-a", blueprint_key="task-a", status=RunStatus.COMPLETED
        )

        result = cli_runner.invoke(
            app, ["-p", str(history_workspace), "history", "show", "session-known", "--format", "json"]
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "event_type": "HistoryShowResult",
            "payload": {
                "status": "ok",
                "session_id": "session-known",
                "run": {
                    "session_id": "session-known",
                    "blueprint_name": "task-a",
                    "status": "completed",
                    "branch_name": None,
                    "started_at": ANY_TIMESTAMP,
                    "completed_at": None,
                    "duration_seconds": None,
                    "error_message": None,
                },
                "checkpoint": None,
                "checkpoint_raw": None,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }
