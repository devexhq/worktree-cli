from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import GitFileSystem, make_cli_context, make_rich_output
from worktree.cli import app
from worktree.cli.sandbox.commands.sandbox_apply import sandbox_apply_command
from worktree.cli.sandbox.formatters import SandboxApplyFormatter
from worktree.core.db import WorktreeDb
from worktree.core.sandbox import (
    Sandbox,
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxApplyStrategy,
)

runner = CliRunner()


class SandboxApplyRenderTests:
    """Renderer unit tests for sandbox apply output formatting."""

    def test_render_apply_success_patch(self) -> None:
        result = SandboxApplyResult(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_8f2a1b9c",
            strategy=SandboxApplyStrategy.PATCH,
            touched_files=["src/app.py", "tests/test_app.py"],
        )
        formatter = SandboxApplyFormatter()
        renderable = formatter.to_rich(result)
        rich_output, buffer = make_rich_output()
        rich_output.add_line(renderable)
        rich_output.print()
        out = buffer.getvalue()
        assert "Applied sandbox sbx_8f2a1b9c to workspace (patch)" in out
        assert "2 files changed" in out
        assert "Status updated: merged" in out

    def test_render_apply_success_squash(self) -> None:
        result = SandboxApplyResult(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_8f2a1b9c",
            strategy=SandboxApplyStrategy.SQUASH,
            commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )
        formatter = SandboxApplyFormatter()
        renderable = formatter.to_rich(result)
        rich_output, buffer = make_rich_output()
        rich_output.add_line(renderable)
        rich_output.print()
        out = buffer.getvalue()
        assert "Applied sandbox sbx_8f2a1b9c to workspace (squash)" in out
        assert "Commit: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2" in out
        assert "Status updated: merged" in out

    def test_render_apply_success_with_cleanup(self) -> None:
        result = SandboxApplyResult(
            status=SandboxApplyStatus.OK,
            sandbox_id="sbx_8f2a1b9c",
            strategy=SandboxApplyStrategy.PATCH,
            touched_files=["file.txt"],
            cleaned_up=True,
        )
        formatter = SandboxApplyFormatter()
        renderable = formatter.to_rich(result)
        rich_output, buffer = make_rich_output()
        rich_output.add_line(renderable)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox worktree and branch deleted" in out

    def test_render_apply_failed(self) -> None:
        result = SandboxApplyResult(
            status=SandboxApplyStatus.CONFLICT,
            sandbox_id="sbx_8f2a1b9c",
            errors=["conflicts detected in src/app.py"],
        )
        formatter = SandboxApplyFormatter()
        renderable = formatter.to_rich(result)
        rich_output, buffer = make_rich_output()
        rich_output.add_line(renderable)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox Apply Failed" in out
        assert "conflicts detected in src/app.py" in out


class SandboxApplyCommandDirectTests:
    """Direct sandbox_apply_command execution tests."""

    def test_sandbox_apply_command_success(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        db = WorktreeDb(path=git_fs.base_path)
        manager = Sandbox(path=git_fs.base_path, db=db.sandboxes)
        create_res = manager.create(session_id="sbx_dir1")
        assert create_res.ok and create_res.session is not None
        session = create_res.session
        (session.sandbox_path / "f.txt").write_text("patch apply\n", encoding="utf-8")

        context = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_apply_command(context, "sbx_dir1")
        assert outcome.ok
        assert (git_fs.base_path / "f.txt").read_text(encoding="utf-8") == "patch apply\n"
        manager.cleanup(session)

    def test_sandbox_apply_command_failure(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        context = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_apply_command(context, "sbx_nonexistent")
        assert not outcome.ok
        assert outcome.errors


class SandboxApplyCliInvocationTests:
    """Typer runner integration tests for `wt sandbox apply`."""

    def test_cli_apply_patch_default(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        db = WorktreeDb(path=git_fs.base_path)
        manager = Sandbox(path=git_fs.base_path, db=db.sandboxes)
        create_res = manager.create(session_id="sbx_cli1")
        assert create_res.ok and create_res.session is not None
        session = create_res.session
        (session.sandbox_path / "new.txt").write_text("cli new\n", encoding="utf-8")

        result = runner.invoke(app, ["sandbox", "apply", "sbx_cli1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Applied sandbox sbx_cli1 to workspace (patch)" in result.stdout
        assert (git_fs.base_path / "new.txt").read_text(encoding="utf-8") == "cli new\n"
        manager.cleanup(session)

    def test_cli_apply_squash_with_message_and_delete(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        db = WorktreeDb(path=git_fs.base_path)
        manager = Sandbox(path=git_fs.base_path, db=db.sandboxes)
        create_res = manager.create(session_id="sbx_cli_sq")
        assert create_res.ok and create_res.session is not None
        session = create_res.session
        (session.sandbox_path / "sq.txt").write_text("sq data\n", encoding="utf-8")

        result = runner.invoke(
            app,
            ["sandbox", "apply", "sbx_cli_sq", "--strategy", "squash", "-m", "feat: sq test", "--delete"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Applied sandbox sbx_cli_sq to workspace (squash)" in result.stdout
        assert "Sandbox worktree and branch deleted" in result.stdout
        assert not session.sandbox_path.exists()

    def test_cli_apply_dry_run(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        db = WorktreeDb(path=git_fs.base_path)
        manager = Sandbox(path=git_fs.base_path, db=db.sandboxes)
        create_res = manager.create(session_id="sbx_cli_dry")
        assert create_res.ok and create_res.session is not None
        session = create_res.session
        (session.sandbox_path / "dry.txt").write_text("dry data\n", encoding="utf-8")

        result = runner.invoke(app, ["sandbox", "apply", "sbx_cli_dry", "--dry-run"], catch_exceptions=False)
        assert result.exit_code == 0
        assert not (git_fs.base_path / "dry.txt").exists()
        manager.cleanup(session)

    def test_cli_apply_not_found(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        result = runner.invoke(app, ["sandbox", "apply", "sbx_ghost"])
        assert result.exit_code == 1
        assert "Sandbox Apply Failed" in result.stdout
        assert "Sandbox 'sbx_ghost' not found" in result.stdout
