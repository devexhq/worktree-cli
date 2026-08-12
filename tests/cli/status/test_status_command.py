"""Tests for the status command."""

from __future__ import annotations

import subprocess

import pytest
import typer

from getworktree.cli.status.command import status_command
from tests.helpers import FileSystem, GitFileSystem


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

        status_command()
        out = capsys.readouterr().out
        assert "Worktree Local Workspace Status" in out
        assert git_fs.base_path.name in out
        assert "feature" in out

    def test_status_without_init_exits(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(fs.base_path)
        with pytest.raises(typer.Exit) as exc:
            status_command()
        assert exc.value.exit_code == 1
