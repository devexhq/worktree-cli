"""CLI smoke tests for the Typer entrypoint."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from getworktree.cli.cli import __version__, app

runner = CliRunner()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    # Create an initial commit so worktrees/branches work reliably.
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return tmp_path


class CliSmokeTests:
    """Smoke tests for top-level CLI behavior."""

    def test_bare_invocation_prints_banner_and_help(self) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Worktree CLI" in result.stdout
        assert "init" in result.stdout

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Worktree CLI" in result.stdout
        assert __version__ in result.stdout

    def test_init_via_cli(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (git_repo / ".worktree" / "config.json").is_file()
        assert (git_repo / ".worktree" / "data.db").is_file()
