"""Tests for the status command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import typer

from getworktree.commands.status.command import status_command
from getworktree.core.config.generator import generate_default_config


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-b", "feature"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


class StatusCommandTests:
    """Tests for status_command."""

    def test_status_with_config(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
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
