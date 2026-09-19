"""Single-tier CLI integration tests for wt sandbox apply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from tests.harness.matchers import assert_model_equal
from worktree.cli import app
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox.facade import Sandbox
from worktree.core.sandbox.models import SandboxApplyResult, SandboxApplyStatus, SandboxApplyStrategy, SandboxSession


def _create_sandbox_with_committed_change(sandbox_workspace: Path) -> SandboxSession:
    """Create a sandbox and commit one file change inside its worktree."""
    create_result = Sandbox(path=sandbox_workspace).create(name="apply-me")
    assert create_result.session is not None
    session = create_result.session

    (session.sandbox_path / "target.py").write_text("changed\n", encoding="utf-8")
    GitRunner.add_all(session.sandbox_path)
    GitRunner.commit(session.sandbox_path, "Sandbox change to target.py")

    return session


class SandboxApplyCliIntegrationTests:
    """Typer runner integration tests for wt sandbox apply."""

    def test_sandbox_apply_cli_patch_strategy_exits_zero(
        self, cli_runner: CliRunner, sandbox_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt sandbox apply <id> (patch strategy) writes the change to the main tree, exits 0, and dispatches the exact SandboxApplyResult DTO."""
        session = _create_sandbox_with_committed_change(sandbox_workspace)

        result = cli_runner.invoke(app, ["-p", str(sandbox_workspace), "sandbox", "apply", session.session_id])

        assert result.exit_code == 0
        assert "Applied sandbox" in result.stdout
        assert (sandbox_workspace / "target.py").read_text(encoding="utf-8") == "changed\n"
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            SandboxApplyResult(
                status=SandboxApplyStatus.OK,
                sandbox_id=session.session_id,
                strategy=SandboxApplyStrategy.PATCH,
                touched_files=["target.py"],
                conflicting_files=[],
                cleaned_up=False,
                commit_sha=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_sandbox_apply_cli_missing_sandbox_exits_one(
        self, cli_runner: CliRunner, sandbox_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt sandbox apply on a missing id exits 1, reports not found, and dispatches the exact NOT_FOUND DTO."""
        result = cli_runner.invoke(app, ["-p", str(sandbox_workspace), "sandbox", "apply", "missing-id"])

        assert result.exit_code == 1
        assert "not found" in result.stdout
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            SandboxApplyResult(
                status=SandboxApplyStatus.NOT_FOUND,
                sandbox_id="missing-id",
                strategy=SandboxApplyStrategy.PATCH,
                touched_files=[],
                conflicting_files=[],
                cleaned_up=False,
                commit_sha=None,
                errors=["Sandbox 'missing-id' not found."],
                warnings=[],
                fixes=["Run `wt sandbox list` to see known sandboxes"],
            ),
        )

    def test_sandbox_apply_cli_renders_json(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        """wt sandbox apply <id> --format json emits a SandboxApplyResult envelope."""
        session = _create_sandbox_with_committed_change(sandbox_workspace)

        result = cli_runner.invoke(
            app, ["-p", str(sandbox_workspace), "sandbox", "apply", session.session_id, "--format", "json"]
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "event_type": "SandboxApplyResult",
            "payload": {
                "status": "ok",
                "sandbox_id": session.session_id,
                "strategy": "patch",
                "touched_files": ["target.py"],
                "conflicting_files": [],
                "cleaned_up": False,
                "commit_sha": None,
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }
