"""Tests for the status command."""

from __future__ import annotations

import subprocess

import pytest
import typer

from tests.helpers import FileSystem, GitFileSystem
from worktree.cli.context import get_cli_context
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

        status_command(context=get_cli_context(cwd=git_fs.base_path))
        out = capsys.readouterr().out
        assert "Worktree Local Workspace Status" in out
        assert git_fs.base_path.name in out
        assert "feature" in out

    def test_status_without_init_exits(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(fs.base_path)
        with pytest.raises(typer.Exit) as exc:
            status_command(context=get_cli_context(cwd=fs.base_path))
        assert exc.value.exit_code == 1
