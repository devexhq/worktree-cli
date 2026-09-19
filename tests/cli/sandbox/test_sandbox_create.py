"""Single-tier CLI integration tests for wt sandbox create."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from tests.harness.matchers import ANY_GIT_SHA, ANY_ISO_TIMESTAMP, ANY_PATH, AnyMatching, assert_model_equal
from worktree.cli import app
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox.models import SandboxCreateResult, SandboxCreateStatus, SandboxSession

# Freshly generated per run (uuid.uuid4().hex[:8]); shape-only, not reused elsewhere in this file.
_ANY_SESSION_ID = AnyMatching(r"sbx_[0-9a-f]{8}", "ANY_SESSION_ID")
_ANY_TARGET_BRANCH = AnyMatching(r"worktree/sandbox-sbx_[0-9a-f]{8}", "ANY_TARGET_BRANCH")


class SandboxCreateCliIntegrationTests:
    """Typer runner integration tests for wt sandbox create."""

    def test_sandbox_create_cli_creates_worktree_and_branch_exits_zero(
        self, cli_runner: CliRunner, sandbox_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt sandbox create --name demo creates the worktree dir and branch, exits 0, and dispatches the exact SandboxCreateResult DTO."""
        result = cli_runner.invoke(
            app,
            ["-p", str(sandbox_workspace), "sandbox", "create", "--name", "demo"],
        )

        assert result.exit_code == 0
        assert "Sandbox created:" in result.stdout

        sandbox_dirs = list((sandbox_workspace / ".worktree" / "sandboxes").iterdir())
        assert len(sandbox_dirs) == 1
        session_id = sandbox_dirs[0].name
        assert sandbox_dirs[0].is_dir()

        branches = GitRunner.list_branches(sandbox_workspace)
        assert f"worktree/sandbox-{session_id}" in branches

        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            SandboxCreateResult.model_construct(
                status=SandboxCreateStatus.OK,
                session=SandboxSession.model_construct(
                    session_id=_ANY_SESSION_ID,
                    target_branch=_ANY_TARGET_BRANCH,
                    sandbox_path=ANY_PATH,
                    base_commit=ANY_GIT_SHA,
                    name="demo",
                    created_at=ANY_ISO_TIMESTAMP,
                    command_passed=None,
                    wip_applied=False,
                    wip_paths=[],
                ),
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_sandbox_create_cli_capacity_exceeded_exits_one(
        self, cli_runner: CliRunner, sandbox_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """A 4th wt sandbox create beyond the default limit of 3 exits 1 and dispatches the exact CAPACITY_EXCEEDED DTO."""
        for _ in range(3):
            create_result = cli_runner.invoke(app, ["-p", str(sandbox_workspace), "sandbox", "create"])
            assert create_result.exit_code == 0

        result = cli_runner.invoke(app, ["-p", str(sandbox_workspace), "sandbox", "create"])

        assert result.exit_code == 1
        assert "Maximum active sandboxes reached (3/3)." in result.stdout
        assert len(dispatch_spy) == 4
        assert_model_equal(
            dispatch_spy[-1],
            SandboxCreateResult(
                status=SandboxCreateStatus.CAPACITY_EXCEEDED,
                session=None,
                errors=["Maximum active sandboxes reached (3/3)."],
                warnings=[],
                fixes=[
                    "Run `wt prune` to remove stale sandboxes, or",
                    "Raise sandbox.max_active_sandboxes in .worktree/config.json",
                ],
            ),
        )

    def test_sandbox_create_cli_renders_json(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        """wt sandbox create --name demo --format json emits a SandboxCreateResult envelope."""
        result = cli_runner.invoke(
            app,
            ["-p", str(sandbox_workspace), "sandbox", "create", "--name", "demo", "--format", "json"],
        )

        assert result.exit_code == 0
        actual_json = json.loads(result.stdout)
        session = actual_json["payload"]["session"]
        for field in ("session_id", "target_branch", "sandbox_path", "base_commit", "created_at"):
            assert session[field]
            session[field] = "placeholder"

        assert actual_json == {
            "event_type": "SandboxCreateResult",
            "payload": {
                "status": "ok",
                "session": {
                    "session_id": "placeholder",
                    "target_branch": "placeholder",
                    "sandbox_path": "placeholder",
                    "base_commit": "placeholder",
                    "name": "demo",
                    "created_at": "placeholder",
                    "command_passed": None,
                    "wip_applied": False,
                    "wip_paths": [],
                },
                "errors": [],
                "warnings": [],
                "fixes": [],
            },
        }

    def test_sandbox_create_cli_with_wip_flag_overlays_and_exits_zero(
        self, cli_runner: CliRunner, sandbox_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt sandbox create --wip binds the flag and dispatches SandboxCreateResult with wip_applied=True."""
        (sandbox_workspace / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")

        result = cli_runner.invoke(
            app,
            ["-p", str(sandbox_workspace), "sandbox", "create", "--name", "wip-demo", "--wip"],
        )

        assert result.exit_code == 0
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            SandboxCreateResult.model_construct(
                status=SandboxCreateStatus.OK,
                session=SandboxSession.model_construct(
                    session_id=_ANY_SESSION_ID,
                    target_branch=_ANY_TARGET_BRANCH,
                    sandbox_path=ANY_PATH,
                    base_commit=ANY_GIT_SHA,
                    name="wip-demo",
                    created_at=ANY_ISO_TIMESTAMP,
                    command_passed=None,
                    wip_applied=True,
                    wip_paths=["dirty.txt"],
                ),
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_sandbox_create_cli_with_base_ref_option_branches_from_specified_target(
        self, cli_runner: CliRunner, sandbox_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt sandbox create --base-ref binds the option and creates a sandbox branching from the specified ref."""
        (sandbox_workspace / "first.txt").write_text("first commit\n", encoding="utf-8")
        GitRunner.add_all(sandbox_workspace)
        GitRunner.commit(sandbox_workspace, "Add first.txt")
        first_commit = GitRunner.rev_parse(sandbox_workspace, rev="HEAD")

        (sandbox_workspace / "second.txt").write_text("second commit\n", encoding="utf-8")
        GitRunner.add_all(sandbox_workspace)
        GitRunner.commit(sandbox_workspace, "Add second.txt")
        current_head = GitRunner.rev_parse(sandbox_workspace, rev="HEAD")
        assert first_commit != current_head

        result = cli_runner.invoke(
            app,
            ["-p", str(sandbox_workspace), "sandbox", "create", "--name", "ref-demo", "--base-ref", first_commit],
        )

        assert result.exit_code == 0
        assert len(dispatch_spy) == 1
        session = dispatch_spy[0].session
        assert_model_equal(
            dispatch_spy[0],
            SandboxCreateResult.model_construct(
                status=SandboxCreateStatus.OK,
                session=SandboxSession.model_construct(
                    session_id=_ANY_SESSION_ID,
                    target_branch=_ANY_TARGET_BRANCH,
                    sandbox_path=ANY_PATH,
                    base_commit=first_commit,
                    name="ref-demo",
                    created_at=ANY_ISO_TIMESTAMP,
                    command_passed=None,
                    wip_applied=False,
                    wip_paths=[],
                ),
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
        assert (session.sandbox_path / "first.txt").read_text(encoding="utf-8") == "first commit\n"
        assert not (session.sandbox_path / "second.txt").exists()
