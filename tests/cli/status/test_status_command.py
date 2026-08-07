"""Tests for the status command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import typer

from getworktree.cli.status.command import status_command
from getworktree.core.config.generator import generate_default_config


class StatusCommandTests:
    """Tests for status_command."""

    def test_status_with_config(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        subprocess.run(["git", "checkout", "feature"], cwd=git_repo, check=True, capture_output=True)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        generate_default_config(config_path, git_repo.name)

        status_command()
        out = capsys.readouterr().out
        assert "Worktree Local Workspace Status" in out
        assert git_repo.name in out
        assert "feature" in out

    def test_status_without_init_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc:
            status_command()
        assert exc.value.exit_code == 1
