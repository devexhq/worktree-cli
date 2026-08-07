"""Tests for `wt sandbox create`."""

from __future__ import annotations

import json
import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import typer
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.sandbox.command import sandbox_create_command
from getworktree.cli.sandbox.renderers import (
    render_sandbox_create_failed,
    render_sandbox_create_success,
)
from getworktree.common.utils import RichOutput
from getworktree.core.config.generator import generate_default_config
from getworktree.core.db import SandboxStatus, get_sandbox, list_sandboxes
from getworktree.core.git_sandbox import (
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
)

runner = CliRunner()
DB_REL = ".worktree/data.db"


def _init_git_repo(path: Path, branch: str = "feature") -> None:
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


def _init_config(repo: Path) -> None:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    assert generate_default_config(config_path, project_name=repo.name).ok


def _rich(*, width: int = 120) -> tuple[RichOutput, StringIO]:
    buffer = StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        color_system=None,
        width=width,
    )
    return RichOutput(console=console), buffer


def _session(
    *,
    session_id: str = "sbx_a1b2c3d4",
    sandbox_path: Path | None = None,
) -> SandboxSession:
    return SandboxSession(
        session_id=session_id,
        target_branch=f"worktree/sandbox-{session_id}",
        sandbox_path=sandbox_path or Path(".worktree/sandboxes") / session_id,
        base_commit="4f2c9a1e8b3d6f0a2c5e7b1d9a3f6c8e0b2d4f6a",
        created_at="2026-08-03T10:00:00+00:00",
    )


class SandboxCreateRenderTests:
    """Renderer unit tests with a fixed console width."""

    def test_success_block(self, tmp_path: Path) -> None:
        session = _session(sandbox_path=tmp_path / ".worktree" / "sandboxes" / "sbx_a1b2c3d4")
        rich_output, buffer = _rich()
        render_sandbox_create_success(session, cwd=tmp_path, rich_output=rich_output)
        out = buffer.getvalue()
        assert "Sandbox created: sbx_a1b2c3d4" in out
        assert "Branch: worktree/sandbox-sbx_a1b2c3d4" in out
        assert "Path: .worktree/sandboxes/sbx_a1b2c3d4" in out

    def test_success_with_warnings(self, tmp_path: Path) -> None:
        session = _session(
            session_id="sbx_warn",
            sandbox_path=tmp_path / ".worktree" / "sandboxes" / "sbx_warn",
        )
        rich_output, buffer = _rich()
        render_sandbox_create_success(
            session,
            warnings=["db write failed"],
            cwd=tmp_path,
            rich_output=rich_output,
        )
        out = buffer.getvalue()
        assert "Sandbox created: sbx_warn" in out
        assert "db write failed" in out
        assert "•" in out

    def test_failed_panel(self) -> None:
        rich_output, buffer = _rich()
        render_sandbox_create_failed(
            ["capacity exceeded detail"],
            rich_output=rich_output,
        )
        out = buffer.getvalue()
        assert "Sandbox Create Failed" in out
        assert "capacity exceeded detail" in out

    def test_failed_panel_empty_errors_fallback(self) -> None:
        rich_output, buffer = _rich()
        render_sandbox_create_failed([], rich_output=rich_output)
        out = buffer.getvalue()
        assert "Sandbox Create Failed" in out
        assert "Sandbox creation failed." in out


class SandboxCreateCommandDirectTests:
    """Direct sandbox_create_command exit-code / side-effect tests."""

    def test_default_create_exits_zero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_create_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0
        out = capsys.readouterr().out
        assert "Sandbox created:" in out
        assert "Branch: worktree/sandbox-" in out
        assert "Path: .worktree/sandboxes/" in out

        rows = list_sandboxes(cwd=git_repo)
        assert len(rows) == 1
        assert rows[0].status is SandboxStatus.ACTIVE

    def test_name_flag(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_create_command(name="  demo  ", cwd=git_repo)
        assert exc_info.value.exit_code == 0
        rows = list_sandboxes(cwd=git_repo)
        assert len(rows) == 1
        assert rows[0].name == "demo"
        assert "Sandbox created:" in capsys.readouterr().out

    def test_base_ref_override(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        subprocess.run(
            ["git", "checkout", "-b", "other"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        (git_repo / "other.txt").write_text("other\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "other.txt"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "other tip"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        feature_tip = subprocess.run(
            ["git", "rev-parse", "feature"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_create_command(base_ref="feature", cwd=git_repo)
        assert exc_info.value.exit_code == 0
        rows = list_sandboxes(cwd=git_repo)
        assert len(rows) == 1
        assert rows[0].base_commit == feature_tip

    def test_wip_flag(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        (git_repo / "f.txt").write_text("dirty\n", encoding="utf-8")
        (git_repo / "new.txt").write_text("untracked\n", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_create_command(wip=True, cwd=git_repo)
        assert exc_info.value.exit_code == 0
        rows = list_sandboxes(cwd=git_repo)
        assert len(rows) == 1
        sandbox_path = Path(rows[0].sandbox_path)
        assert (sandbox_path / "f.txt").read_text(encoding="utf-8") == "dirty\n"
        assert (sandbox_path / "new.txt").read_text(encoding="utf-8") == "untracked\n"

    @pytest.mark.parametrize(
        ("status", "errors"),
        [
            (SandboxCreateStatus.NOT_INITIALIZED, ["not initialized detail"]),
            (SandboxCreateStatus.UNREADABLE_CONFIG, ["unreadable detail"]),
            (SandboxCreateStatus.CAPACITY_EXCEEDED, ["capacity detail"]),
            (SandboxCreateStatus.GIT_FAILED, ["git failed detail"]),
            (SandboxCreateStatus.WIP_FAILED, ["wip failed detail"]),
        ],
    )
    def test_failure_statuses_exit_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        status: SandboxCreateStatus,
        errors: list[str],
    ) -> None:
        monkeypatch.chdir(git_repo)

        mock_manager = MagicMock()
        mock_manager.create_sandbox_result.return_value = SandboxCreateResult(
            status=status,
            errors=errors,
        )
        monkeypatch.setattr(
            "getworktree.cli.sandbox.command.GitSandboxManager",
            lambda cwd=None: mock_manager,
        )

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_create_command(cwd=git_repo)
        assert exc_info.value.exit_code == 1
        out = capsys.readouterr().out
        assert "Sandbox Create Failed" in out
        assert errors[0] in out

    def test_warnings_on_success_exit_zero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        session = _session(
            session_id="sbx_warnok",
            sandbox_path=git_repo / ".worktree" / "sandboxes" / "sbx_warnok",
        )
        mock_manager = MagicMock()
        mock_manager.create_sandbox_result.return_value = SandboxCreateResult(
            status=SandboxCreateStatus.OK,
            session=session,
            warnings=["Failed to persist sandbox metadata to the local database: boom"],
        )
        monkeypatch.setattr(
            "getworktree.cli.sandbox.command.GitSandboxManager",
            lambda cwd=None: mock_manager,
        )

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_create_command(cwd=git_repo)
        assert exc_info.value.exit_code == 0
        out = capsys.readouterr().out
        assert "Sandbox created: sbx_warnok" in out
        assert "Failed to persist sandbox metadata" in out


class SandboxCreateCliTests:
    """CliRunner coverage for Typer wiring and integration."""

    def test_help_lists_create(self) -> None:
        result = runner.invoke(app, ["sandbox", "--help"])
        assert result.exit_code == 0

        sandbox_cmd = get_command(app).get_command(None, "sandbox")
        assert "create" in sandbox_cmd.list_commands(None)
        assert "list" in sandbox_cmd.list_commands(None)
        assert "show" in sandbox_cmd.list_commands(None)

    def test_create_help_options(self) -> None:
        result = runner.invoke(app, ["sandbox", "create", "--help"])
        assert result.exit_code == 0

        create_cmd = get_command(app).get_command(None, "sandbox").get_command(None, "create")
        assert create_cmd.help == "Create an isolated git worktree sandbox."
        opts: set[str] = set()
        for param in create_cmd.params:
            opts.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            opts.update(secondary)
        assert "--name" in opts
        assert "--base-ref" in opts
        assert "--wip" in opts
        assert "--no-wip" in opts

    def test_create_appears_in_list_and_show(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)

        created = runner.invoke(
            app,
            ["sandbox", "create", "--name", "integration"],
        )
        assert created.exit_code == 0
        assert "Sandbox created:" in created.stdout

        rows = list_sandboxes(cwd=git_repo)
        assert len(rows) == 1
        sandbox_id = rows[0].id
        assert rows[0].name == "integration"
        assert get_sandbox(sandbox_id, cwd=git_repo) is not None

        listed = runner.invoke(app, ["sandbox", "list"])
        assert listed.exit_code == 0
        assert sandbox_id in listed.stdout
        assert "integration" in listed.stdout

        shown = runner.invoke(app, ["sandbox", "show", sandbox_id])
        assert shown.exit_code == 0
        assert sandbox_id in shown.stdout
        assert "integration" in shown.stdout
        assert "present" in shown.stdout
        assert "active" in shown.stdout

    def test_create_not_initialized_via_cli(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["sandbox", "create"])
        assert result.exit_code == 1
        assert "Sandbox Create Failed" in result.stdout

    def test_create_invalid_base_ref_via_cli(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        result = runner.invoke(
            app,
            ["sandbox", "create", "--base-ref", "refs/does-not-exist"],
        )
        assert result.exit_code == 1
        assert "Sandbox Create Failed" in result.stdout

    def test_create_capacity_exceeded_via_cli(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        config_path = git_repo / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["sandbox"]["max_active_sandboxes"] = 1
        config_path.write_text(json.dumps(data), encoding="utf-8")

        first = runner.invoke(app, ["sandbox", "create", "--name", "one"])
        assert first.exit_code == 0

        second = runner.invoke(app, ["sandbox", "create", "--name", "two"])
        assert second.exit_code == 1
        assert "Sandbox Create Failed" in second.stdout
