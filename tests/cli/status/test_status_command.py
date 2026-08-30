"""Tests for the status command."""

from __future__ import annotations

import subprocess

import pytest

from tests.helpers import FileSystem, GitFileSystem, make_cli_context
from worktree.cli.status.commands.root import status_command


class StatusCommandTests:
    """Tests for status_command."""

    def test_status_with_config(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        subprocess.run(
            ["git", "checkout", "-b", "feature-cmd"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
        )
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = status_command(ctx)
        assert outcome.ok
        assert outcome.result is not None
        assert outcome.errors == []

        ctx.output.print()
        out = capsys.readouterr().out
        assert "Worktree Workspace Status" in out
        assert git_fs.base_path.name in out
        assert "feature-cmd" in out

    def test_status_without_init(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(fs.base_path)
        ctx = make_cli_context(cwd=fs.base_path)
        outcome = status_command(ctx)

        assert outcome.ok
        assert outcome.result is not None
        assert not outcome.result.is_initialized

        ctx.output.print()
        out = capsys.readouterr().out
        assert "Worktree Workspace Status" in out
        assert "not_found" in out
        assert "Worktree workspace is not initialized" in out

    def test_status_handles_exception(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def _failing_collector(*args: object, **kwargs: object) -> None:
            raise RuntimeError("collector boom")

        monkeypatch.setattr("worktree.cli.status.commands.root.collect_status", _failing_collector)

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = status_command(ctx)

        assert not outcome.ok
        assert outcome.result is None
        assert "collector boom" in outcome.errors

        ctx.output.print()
        out = capsys.readouterr().out
        assert "Status Error" in out
        assert "collector boom" in out
