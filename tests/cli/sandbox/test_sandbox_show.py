"""Single-tier CLI integration tests for wt sandbox show."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from tests.harness.matchers import ANY_TIMESTAMP, assert_model_equal
from worktree.cli import app
from worktree.core.db import SandboxRecord, SandboxStatus
from worktree.core.sandbox.facade import Sandbox
from worktree.core.sandbox.models import SandboxShowResult, SandboxShowStatus


class SandboxShowCliIntegrationTests:
    """Typer runner integration tests for wt sandbox show."""

    def test_sandbox_show_cli_existing_sandbox_exits_zero(
        self, cli_runner: CliRunner, sandbox_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt sandbox show <id> on an existing sandbox exits 0, renders its session_id, and dispatches the exact record."""
        create_result = Sandbox(path=sandbox_workspace).create(name="show-me")
        assert create_result.session is not None
        session = create_result.session

        result = cli_runner.invoke(app, ["-p", str(sandbox_workspace), "sandbox", "show", session.session_id])

        assert result.exit_code == 0
        assert session.session_id in result.stdout
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            SandboxShowResult(
                status=SandboxShowStatus.OK,
                sandbox=SandboxRecord.model_construct(
                    id=session.session_id,
                    name="show-me",
                    branch_name=session.target_branch,
                    base_commit=session.base_commit,
                    sandbox_path=session.sandbox_path,
                    status=SandboxStatus.ACTIVE,
                    created_at=ANY_TIMESTAMP,
                    updated_at=ANY_TIMESTAMP,
                ),
                disk_present=True,
                reconciled=False,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_sandbox_show_cli_missing_sandbox_exits_one(
        self, cli_runner: CliRunner, sandbox_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt sandbox show on a missing id exits 1, reports not found, and dispatches the exact NOT_FOUND DTO."""
        result = cli_runner.invoke(app, ["-p", str(sandbox_workspace), "sandbox", "show", "missing-id"])

        assert result.exit_code == 1
        assert "not found" in result.stdout
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            SandboxShowResult(
                status=SandboxShowStatus.NOT_FOUND,
                sandbox=None,
                disk_present=False,
                reconciled=False,
                errors=["Sandbox 'missing-id' not found."],
                warnings=[],
                fixes=["Run `wt sandbox list` to see known sandboxes"],
            ),
        )

    def test_sandbox_show_cli_renders_json(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        """wt sandbox show <id> --format json emits a SandboxShowResult envelope matching the seeded record."""
        create_result = Sandbox(path=sandbox_workspace).create(name="show-me")
        assert create_result.session is not None
        session = create_result.session

        result = cli_runner.invoke(
            app,
            ["-p", str(sandbox_workspace), "sandbox", "show", session.session_id, "--format", "json"],
        )

        assert result.exit_code == 0
        actual_json = json.loads(result.stdout)
        sandbox = actual_json["payload"]["sandbox"]
        for field in ("created_at", "updated_at"):
            assert sandbox[field]
            sandbox[field] = "placeholder"

        assert actual_json == {
            "event_type": "SandboxShowResult",
            "payload": {
                "status": "ok",
                "sandbox": {
                    "id": session.session_id,
                    "name": "show-me",
                    "branch_name": session.target_branch,
                    "base_commit": session.base_commit,
                    "sandbox_path": str(session.sandbox_path),
                    "status": "active",
                    "created_at": "placeholder",
                    "updated_at": "placeholder",
                },
                "disk_present": True,
                "reconciled": False,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }
