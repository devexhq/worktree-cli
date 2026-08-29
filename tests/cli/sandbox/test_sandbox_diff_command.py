from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import GitFileSystem, make_cli_context, make_rich_output
from worktree.cli import app
from worktree.cli.sandbox.commands.sandbox_diff import sandbox_diff_command
from worktree.cli.sandbox.renderers import render_sandbox_diff
from worktree.core.db import WorktreeDb
from worktree.core.sandbox import (
    GitSandboxManager,
    SandboxDiffResult,
    SandboxDiffStatus,
)

runner = CliRunner()


class SandboxDiffRenderTests:
    """Renderer unit tests for sandbox diff output formatting."""

    def test_render_diff_success(self) -> None:
        result = SandboxDiffResult(
            status=SandboxDiffStatus.OK,
            sandbox_id="sbx_8f2a1b9c",
            diff_text="diff --git a/f.txt b/f.txt\n--- a/f.txt\n+++ b/f.txt\n@@ -1 +1 @@\n-old\n+new",
            stat_text="f.txt | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)",
            files_changed=["f.txt"],
        )
        rich_output, buffer = make_rich_output()
        render_sandbox_diff(result, stat=False, output=rich_output)
        rich_output.print()
        out = buffer.getvalue()
        assert "diff --git a/f.txt b/f.txt" in out

    def test_render_diff_stat(self) -> None:
        result = SandboxDiffResult(
            status=SandboxDiffStatus.OK,
            sandbox_id="sbx_8f2a1b9c",
            diff_text="diff --git a/f.txt b/f.txt\n",
            stat_text="f.txt | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)",
            files_changed=["f.txt"],
        )
        rich_output, buffer = make_rich_output()
        render_sandbox_diff(result, stat=True, output=rich_output)
        rich_output.print()
        out = buffer.getvalue()
        assert "f.txt | 2 +-" in out

    def test_render_diff_empty(self) -> None:
        result = SandboxDiffResult(
            status=SandboxDiffStatus.EMPTY_DIFF,
            sandbox_id="sbx_8f2a1b9c",
        )
        rich_output, buffer = make_rich_output()
        render_sandbox_diff(result, stat=False, output=rich_output)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox 'sbx_8f2a1b9c' has no changes compared to base commit." in out

    def test_render_diff_failed(self) -> None:
        result = SandboxDiffResult(
            status=SandboxDiffStatus.NOT_FOUND,
            sandbox_id="sbx_8f2a1b9c",
            errors=["Sandbox 'sbx_8f2a1b9c' not found."],
        )
        rich_output, buffer = make_rich_output()
        render_sandbox_diff(result, stat=False, output=rich_output)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox Diff Failed" in out
        assert "Sandbox 'sbx_8f2a1b9c' not found." in out


class SandboxDiffCommandDirectTests:
    """Direct sandbox_diff_command execution tests."""

    def test_sandbox_diff_command_success(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        db = WorktreeDb(path=git_fs.base_path)
        manager = GitSandboxManager(path=git_fs.base_path, db=db.sandboxes)
        create_res = manager.create_sandbox(session_id="sbx_diff_cmd")
        assert create_res.ok and create_res.session is not None
        session = create_res.session
        (session.sandbox_path / "hello.py").write_text("hello = True\n", encoding="utf-8")

        context = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_diff_command(context, "sbx_diff_cmd")
        assert outcome.ok
        assert outcome.result is not None
        assert "hello.py" in outcome.result.files_changed
        manager.cleanup_sandbox(session)


class SandboxDiffCliInvocationTests:
    """Typer runner integration tests for `wt sandbox diff`."""

    def test_cli_diff_default(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        db = WorktreeDb(path=git_fs.base_path)
        manager = GitSandboxManager(path=git_fs.base_path, db=db.sandboxes)
        create_res = manager.create_sandbox(session_id="sbx_cli_diff")
        assert create_res.ok and create_res.session is not None
        session = create_res.session
        (session.sandbox_path / "cli_diff.txt").write_text("cli diff content\n", encoding="utf-8")

        result = runner.invoke(app, ["sandbox", "diff", "sbx_cli_diff"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "cli_diff.txt" in result.stdout
        manager.cleanup_sandbox(session)

    def test_cli_diff_stat(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        db = WorktreeDb(path=git_fs.base_path)
        manager = GitSandboxManager(path=git_fs.base_path, db=db.sandboxes)
        create_res = manager.create_sandbox(session_id="sbx_cli_stat")
        assert create_res.ok and create_res.session is not None
        session = create_res.session
        (session.sandbox_path / "stat_file.txt").write_text("stat content\n", encoding="utf-8")

        result = runner.invoke(app, ["sandbox", "diff", "sbx_cli_stat", "--stat"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "stat_file.txt | 1 +" in result.stdout
        manager.cleanup_sandbox(session)

    def test_cli_diff_not_found(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        result = runner.invoke(app, ["sandbox", "diff", "sbx_unknown"])
        assert result.exit_code == 1
        assert "Sandbox Diff Failed" in result.stdout
