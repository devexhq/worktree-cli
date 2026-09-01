"""Tests for `wt sandbox create`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from tests.helpers import FileSystem, GitFileSystem, make_cli_context, make_rich_output
from worktree.cli import app
from worktree.cli.sandbox.commands.sandbox_create import sandbox_create_command
from worktree.cli.sandbox.formatters import SandboxCreateFormatter
from worktree.core.db import SandboxStatus, WorktreeDb
from worktree.core.sandbox import (
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
)

runner = CliRunner()
DB_REL = ".worktree/data.db"


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
    """Renderer unit tests using SandboxCreateFormatter."""

    def test_success_block(self, fs: FileSystem) -> None:
        session = _session(sandbox_path=fs.base_path / ".worktree" / "sandboxes" / "sbx_a1b2c3d4")
        data = SandboxCreateResult(status=SandboxCreateStatus.OK, session=session)
        formatter = SandboxCreateFormatter()
        renderable = formatter.to_rich(data)
        rich_output, buffer = make_rich_output()
        rich_output.add_line(renderable)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox created: sbx_a1b2c3d4" in out
        assert "Path:" in out
        assert ".worktree/sandboxes/sbx_a1b2c3d4" in out

    def test_success_with_warnings(self, fs: FileSystem) -> None:
        session = _session(
            session_id="sbx_warn",
            sandbox_path=fs.base_path / ".worktree" / "sandboxes" / "sbx_warn",
        )
        data = SandboxCreateResult(status=SandboxCreateStatus.OK, session=session, warnings=["db write failed"])
        formatter = SandboxCreateFormatter()
        renderable = formatter.to_rich(data)
        rich_output, buffer = make_rich_output()
        rich_output.add_line(renderable)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox created: sbx_warn" in out
        assert "db write failed" in out
        assert "•" in out

    def test_failed_panel(self) -> None:
        data = SandboxCreateResult(status=SandboxCreateStatus.CAPACITY_EXCEEDED, errors=["capacity exceeded detail"])
        formatter = SandboxCreateFormatter()
        renderable = formatter.to_rich(data)
        rich_output, buffer = make_rich_output()
        rich_output.add_line(renderable)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox Create Failed" in out
        assert "capacity exceeded detail" in out

    def test_failed_panel_empty_errors_fallback(self) -> None:
        data = SandboxCreateResult(status=SandboxCreateStatus.GIT_FAILED, errors=[])
        formatter = SandboxCreateFormatter()
        renderable = formatter.to_rich(data)
        rich_output, buffer = make_rich_output()
        rich_output.add_line(renderable)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox Create Failed" in out
        assert "Sandbox creation failed." in out


class SandboxCreateCommandDirectTests:
    """Direct sandbox_create_command exit-code / side-effect tests."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path, db_rel_path=DB_REL)

    def test_default_create_exits_zero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_create_command(ctx)
        assert outcome.ok
        ctx.output.print()
        out = capsys.readouterr().out
        assert "Sandbox created:" in out
        assert "Branch: worktree/sandbox-" in out
        assert "Path: .worktree/sandboxes/" in out

        rows = self.db.sandboxes.list()
        assert len(rows) == 1
        assert rows[0].status is SandboxStatus.ACTIVE

    def test_name_flag(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_create_command(ctx, name="  demo  ")
        assert outcome.ok
        ctx.output.print()
        rows = self.db.sandboxes.list()
        assert len(rows) == 1
        assert rows[0].name == "demo"
        assert "Sandbox created:" in capsys.readouterr().out

    def test_base_ref_override(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        subprocess.run(
            ["git", "checkout", "-b", "other"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        )
        (git_fs.base_path / "other.txt").write_text("other\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "other.txt"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "other tip"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        )
        feature_tip = subprocess.run(
            ["git", "rev-parse", "feature"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_create_command(ctx, base_ref="feature")
        assert outcome.ok
        rows = self.db.sandboxes.list()
        assert len(rows) == 1
        assert rows[0].base_commit == feature_tip

    def test_wip_flag(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        (git_fs.base_path / "f.txt").write_text("dirty\n", encoding="utf-8")
        (git_fs.base_path / "new.txt").write_text("untracked\n", encoding="utf-8")

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_create_command(ctx, wip=True)
        assert outcome.ok
        rows = self.db.sandboxes.list()
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
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        status: SandboxCreateStatus,
        errors: list[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        mock_manager = MagicMock()
        mock_manager.create_sandbox.return_value = SandboxCreateResult(
            status=status,
            errors=errors,
        )
        monkeypatch.setattr(
            "worktree.cli.sandbox.commands.sandbox_create.GitSandboxManager",
            lambda cwd=None, **_kwargs: mock_manager,
        )

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_create_command(ctx)
        assert not outcome.ok
        ctx.output.print()
        out = capsys.readouterr().out
        assert "Sandbox Create Failed" in out
        assert errors[0] in out

    def test_warnings_on_success_exit_zero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        session = _session(
            session_id="sbx_warnok",
            sandbox_path=git_fs.base_path / ".worktree" / "sandboxes" / "sbx_warnok",
        )
        mock_manager = MagicMock()
        mock_manager.create_sandbox.return_value = SandboxCreateResult(
            status=SandboxCreateStatus.OK,
            session=session,
            warnings=["Failed to persist sandbox metadata to the local database: boom"],
        )
        monkeypatch.setattr(
            "worktree.cli.sandbox.commands.sandbox_create.GitSandboxManager",
            lambda cwd=None, **_kwargs: mock_manager,
        )

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_create_command(ctx)
        assert outcome.ok
        ctx.output.print()
        out = capsys.readouterr().out
        assert "Sandbox created: sbx_warnok" in out
        assert "Failed to persist sandbox metadata" in out


class SandboxCreateCliTests:
    """CliRunner coverage for Typer wiring and integration."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path, db_rel_path=DB_REL)

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

    def test_create_appears_in_list_and_show(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        created = runner.invoke(
            app,
            ["sandbox", "create", "--name", "integration"],
        )
        assert created.exit_code == 0
        assert "Sandbox created:" in created.stdout

        rows = self.db.sandboxes.list()
        assert len(rows) == 1
        sandbox_id = rows[0].id
        assert rows[0].name == "integration"
        assert self.db.sandboxes.get(sandbox_id) is not None

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

    def test_create_not_initialized_via_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        result = runner.invoke(app, ["sandbox", "create"])
        assert result.exit_code == 1
        assert "Worktree workspace is not initialized" in result.stdout or "Sandbox Create Failed" in result.stdout

    def test_create_invalid_base_ref_via_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        result = runner.invoke(
            app,
            ["sandbox", "create", "--base-ref", "refs/does-not-exist"],
        )
        assert result.exit_code == 1
        assert "Sandbox Create Failed" in result.stdout

    def test_create_capacity_exceeded_via_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["sandbox"]["max_active_sandboxes"] = 1
        config_path.write_text(json.dumps(data), encoding="utf-8")

        first = runner.invoke(app, ["sandbox", "create", "--name", "one"])
        assert first.exit_code == 0

        second = runner.invoke(app, ["sandbox", "create", "--name", "two"])
        assert second.exit_code == 1
        assert "Sandbox Create Failed" in second.stdout
