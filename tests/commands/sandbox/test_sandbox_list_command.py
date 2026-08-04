"""Tests for `wt sandbox list`."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.sandbox.command import (
    collect_sandbox_list,
    sandbox_list_command,
)
from getworktree.commands.sandbox.models import SandboxListStatus
from getworktree.core.config.generator import generate_default_config
from getworktree.core.db import (
    SandboxStatus,
    get_sandbox,
    insert_sandbox,
    update_sandbox_status,
)

runner = CliRunner()
DB_REL = ".worktree/token_audit.db"


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


def _init_config(repo: Path) -> None:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    assert generate_default_config(config_path, project_name=repo.name).ok


def _insert(
    repo: Path,
    *,
    sandbox_id: str,
    name: str | None = None,
    path_suffix: str,
    create_dir: bool = True,
):
    sandbox_path = repo / ".worktree" / "sandboxes" / path_suffix
    if create_dir:
        sandbox_path.mkdir(parents=True, exist_ok=True)
    return insert_sandbox(
        id=sandbox_id,
        branch_name=f"worktree/sandbox-{sandbox_id}",
        base_commit="abc123",
        sandbox_path=sandbox_path,
        name=name,
        cwd=repo,
        db_rel_path=DB_REL,
    )


class SandboxListCommandDirectTests:
    """Direct sandbox_list_command / collect_sandbox_list tests."""

    def test_not_initialized_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Worktree Not Initialized" in out
        assert "CONFIG_NOT_FOUND" in out or "not found" in out.lower()
        assert not (git_repo / DB_REL).exists()

    def test_empty_state(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "No sandboxes found." in out
        assert "Worktree Sandboxes" not in out

    def test_multiple_rows_sorted_by_created_at_desc(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        first = _insert(git_repo, sandbox_id="sbx_first", name=None, path_suffix="1")
        time.sleep(1.1)
        second = _insert(
            git_repo, sandbox_id="sbx_second", name="beta", path_suffix="2"
        )

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Worktree Sandboxes" in out
        assert "ID" in out and "Name" in out and "Branch" in out
        assert "Status" in out and "Created" in out
        assert out.index(second.id) < out.index(first.id)
        assert second.name is not None and second.name in out
        assert "-" in out  # unset name renders as dim "-"
        assert first.created_at in out
        assert second.created_at in out

    def test_status_filter(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        active = _insert(git_repo, sandbox_id="sbx_active", path_suffix="a")
        cleaned = _insert(git_repo, sandbox_id="sbx_cleaned", path_suffix="c")
        update_sandbox_status(
            cleaned.id,
            SandboxStatus.CLEANED,
            cwd=git_repo,
            db_rel_path=DB_REL,
        )

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(status="cleaned", cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert cleaned.id in out
        assert active.id not in out

    def test_reconciles_stale_active_missing_directory(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        stale = _insert(
            git_repo,
            sandbox_id="sbx_stale",
            path_suffix="gone",
            create_dir=False,
        )
        assert not Path(stale.sandbox_path).exists()

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert stale.id in out
        assert "cleaned" in out
        loaded = get_sandbox(stale.id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED

    def test_status_filter_after_reconciliation(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        stale = _insert(
            git_repo,
            sandbox_id="sbx_stale_filter",
            path_suffix="missing",
            create_dir=False,
        )

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(status="active", cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "No sandboxes found." in out
        assert stale.id not in out
        loaded = get_sandbox(stale.id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED

    def test_collect_invalid_config_is_not_initialized(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{not-json", encoding="utf-8")

        result = collect_sandbox_list(cwd=git_repo)
        assert result.status is SandboxListStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert not (git_repo / DB_REL).exists()


class SandboxListCliTests:
    """CliRunner coverage for Typer wiring."""

    def test_help_lists_sandbox_group(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["sandbox", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "Inspect and manage git worktree sandboxes" in result.stdout

    def test_list_help(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["sandbox", "list", "--help"])
        assert result.exit_code == 0
        assert "--status" in result.stdout

    def test_invalid_status_rejected_by_typer(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        result = runner.invoke(app, ["sandbox", "list", "--status", "bogus"])
        assert result.exit_code != 0
        combined = result.stdout + result.stderr
        assert "bogus" in combined.lower() or "invalid" in combined.lower()

    def test_list_via_cli_empty(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        result = runner.invoke(app, ["sandbox", "list"])
        assert result.exit_code == 0
        assert "No sandboxes found." in result.stdout
