"""Tests for `wt loop list`."""

from __future__ import annotations

import subprocess
from importlib import resources
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.loop.command import loop_list_command
from getworktree.core.config.generator import generate_default_config
from getworktree.core.loops.seeder import seed_starter_loops

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
    return tmp_path


def _init_with_loops(repo: Path) -> Path:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    assert generate_default_config(config_path, project_name=repo.name).ok
    loops_dir = repo / ".worktree" / "loops"
    assert seed_starter_loops(loops_dir).ok
    return loops_dir


def _template_text(name: str) -> str:
    root = resources.files("getworktree.core.templates.loops")
    with root.joinpath(name).open(encoding="utf-8") as handle:
        return handle.read()


class LoopListCommandDirectTests:
    """Direct loop_list_command tests."""

    def test_success_seeded_loops(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            loop_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Worktree Loops" in out
        assert "fix-tests" in out
        assert "review-fix" in out
        assert "Loop List Failed" not in out

    def test_empty_loops_directory(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        assert generate_default_config(config_path, project_name=git_repo.name).ok
        loops_dir = git_repo / ".worktree" / "loops"
        loops_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(typer.Exit) as exc_info:
            loop_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "No loops found." in out

    def test_uninitialized_repo_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            loop_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Loop List Failed" in out

    def test_mixed_valid_and_invalid_loops(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        loops_dir = _init_with_loops(git_repo)
        bad_file = loops_dir / "broken.yml"
        bad_file.write_text("version: [\n", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            loop_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Worktree Loops" in out
        assert "fix-tests" in out
        assert "Invalid loop file" in out
        assert "broken.yml" in out

    def test_duplicate_name_warning(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        loops_dir = _init_with_loops(git_repo)
        dup_file = loops_dir / "fix-tests-copy.yml"
        dup_file.write_text(_template_text("fix-tests.yml"), encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            loop_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Worktree Loops" in out
        assert "Warning: Duplicate loop name 'fix-tests'" in out


class LoopListCliTests:
    """CliRunner coverage for registration and help."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["loop", "list", "--help"])
        assert result.exit_code == 0
        assert "List available loop definitions" in result.stdout

    def test_cli_success(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        result = runner.invoke(app, ["loop", "list"])
        assert result.exit_code == 0
        assert "Worktree Loops" in result.stdout
        assert "fix-tests" in result.stdout

    def test_cli_uninitialized(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["loop", "list"])
        assert result.exit_code == 1
        assert "Loop List Failed" in result.stdout
