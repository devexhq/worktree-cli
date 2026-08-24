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
        subprocess.run(["git", "checkout", "feature"], cwd=git_fs.base_path, check=True, capture_output=True)
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = status_command(ctx)
        assert outcome.ok
        ctx.output.print()
        out = capsys.readouterr().out
        assert "Worktree Local Workspace Status" in out
        assert git_fs.base_path.name in out
        assert "feature" in out

    def test_status_without_init_exits(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(fs.base_path)
        ctx = make_cli_context(cwd=fs.base_path)
        outcome = status_command(ctx)
        assert not outcome.ok
