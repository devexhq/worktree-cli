"""Single-tier CLI integration tests for wt resume."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tests.harness.catalog import write_runnable_blueprint
from worktree.cli import app
from worktree.core.db import RunStatus, WorktreeDb
from worktree.core.runtime.models import RunCheckpoint


def _seed_paused_session(
    resume_workspace: Path, *, session_id: str, blueprint_key: str, pending_step_id: str, next_step_index: int
) -> None:
    """Insert a RUNNING run row, then a saved checkpoint that pauses it."""
    db = WorktreeDb(path=resume_workspace)
    db.runs.create(
        session_id=session_id, blueprint_name=blueprint_key, blueprint_key=blueprint_key, status=RunStatus.RUNNING
    )
    checkpoint = RunCheckpoint(
        next_step_index=next_step_index,
        pending_step_id=pending_step_id,
        diagnostic="Step failed during interactive prompt.",
        use_sandbox=False,
    )
    db.runs.save_pause(session_id, checkpoint.model_dump_json(), checkpoint.diagnostic)


class ResumeCliIntegrationTests:
    """Typer runner integration tests for wt resume."""

    def test_resume_cli_from_checkpoint_completes_remaining_steps_exits_zero(
        self, cli_runner: CliRunner, resume_workspace: Path
    ) -> None:
        """wt resume <session_id>: paused checkpoint with use_sandbox=False resumes and completes, exit 0, run record status becomes COMPLETED."""
        write_runnable_blueprint(
            resume_workspace,
            key="resume-task",
            steps=[
                {"id": "s1", "run": "true"},
                {"id": "s2", "run": "true", "on_failure": "continue"},
                {"id": "s3", "run": "touch resumed.marker"},
            ],
        )
        _seed_paused_session(
            resume_workspace,
            session_id="paused-session-1",
            blueprint_key="resume-task",
            pending_step_id="s2",
            next_step_index=1,
        )

        result = cli_runner.invoke(app, ["-p", str(resume_workspace), "resume", "paused-session-1"])

        assert result.exit_code == 0
        record = WorktreeDb(path=resume_workspace).runs.get("paused-session-1")
        assert record is not None
        assert record.status == RunStatus.COMPLETED
        assert (resume_workspace / "resumed.marker").exists()

    def test_resume_cli_unknown_session_exits_one(self, cli_runner: CliRunner, resume_workspace: Path) -> None:
        """wt resume <unknown-id>: no matching paused session, exit 1, 'Resume Failed' in stdout."""
        result = cli_runner.invoke(app, ["-p", str(resume_workspace), "resume", "does-not-exist"])

        assert result.exit_code == 1
        assert "Resume Failed" in result.stdout

    def test_resume_cli_json_format_emits_run_success_event(
        self, cli_runner: CliRunner, resume_workspace: Path
    ) -> None:
        """wt resume <session_id> --format json: NDJSON stream includes a RunSuccessEvent with payload.status == 'completed'."""
        write_runnable_blueprint(
            resume_workspace,
            key="resume-json-task",
            steps=[
                {"id": "s1", "run": "true"},
                {"id": "s2", "run": "true", "on_failure": "continue"},
            ],
        )
        _seed_paused_session(
            resume_workspace,
            session_id="paused-session-2",
            blueprint_key="resume-json-task",
            pending_step_id="s2",
            next_step_index=1,
        )

        result = cli_runner.invoke(app, ["-p", str(resume_workspace), "resume", "paused-session-2", "--format", "json"])

        assert result.exit_code == 0
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        success_events = [e for e in events if e["event_type"] == "RunSuccessEvent"]
        assert len(success_events) == 1
        assert success_events[0]["payload"]["status"] == "completed"
