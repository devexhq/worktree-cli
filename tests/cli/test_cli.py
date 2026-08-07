"""CLI smoke tests for the Typer entrypoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from getworktree.cli.cli import __version__, app

runner = CliRunner()


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
