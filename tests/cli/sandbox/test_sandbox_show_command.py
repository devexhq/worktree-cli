"""Tests for `wt sandbox show`."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from tests.helpers import GitFileSystem, make_cli_context, render_rich, seed_sandbox
from worktree.cli import app
from worktree.cli.sandbox.commands.sandbox_show import (
    sandbox_show_command,
)
from worktree.cli.sandbox.formatters import SandboxShowFormatter
from worktree.core.db import (
    SandboxRecord,
    SandboxStatus,
    WorktreeDb,
)
from worktree.core.sandbox import (
    SandboxShowResult,
    SandboxShowStatus,
)
from worktree.core.sandbox.services.show import collect_sandbox_show

runner = CliRunner()
DB_REL = ".worktree/data.db"


class SandboxShowCollectTests:
    """Tests for collect_sandbox_show (data path, no Rich width coupling)."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path, db_rel_path=DB_REL)

    def test_missing_row_returns_not_found(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        result = collect_sandbox_show(git_fs.base_path, self.db.sandboxes, "sbx_missing")
        assert result.status is SandboxShowStatus.NOT_FOUND
        assert not result.ok
        assert result.sandbox is None

    def test_active_and_present(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        seed_sandbox(self.db.sandboxes, sandbox_id="sbx_present")
        sbx_dir = git_fs.base_path / ".worktree" / "sandboxes" / "sbx_present"
        sbx_dir.mkdir(parents=True, exist_ok=True)

        result = collect_sandbox_show(git_fs.base_path, self.db.sandboxes, "sbx_present")
        assert result.status is SandboxShowStatus.OK
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.id == "sbx_present"
        assert result.sandbox.status is SandboxStatus.ACTIVE
        assert result.disk_present
        assert not result.reconciled

    def test_reconciles_stale_active_missing_directory(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        seed_sandbox(self.db.sandboxes, sandbox_id="sbx_stale", create_dir=False)

        result = collect_sandbox_show(git_fs.base_path, self.db.sandboxes, "sbx_stale")
        assert result.status is SandboxShowStatus.OK
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.id == "sbx_stale"
        assert result.sandbox.status is SandboxStatus.CLEANED
        assert not result.disk_present
        assert result.reconciled

        persisted = self.db.sandboxes.get("sbx_stale")
        assert persisted is not None
        assert persisted.status is SandboxStatus.CLEANED

    def test_leaves_merged_unchanged_even_if_directory_missing(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        row = seed_sandbox(
            self.db.sandboxes,
            sandbox_id="sbx_merged",
            create_dir=False,
        )
        self.db.sandboxes.update_status(row.id, SandboxStatus.MERGED)

        result = collect_sandbox_show(git_fs.base_path, self.db.sandboxes, "sbx_merged")
        assert result.status is SandboxShowStatus.OK
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.status is SandboxStatus.MERGED
        assert not result.disk_present
        assert not result.reconciled

        persisted = self.db.sandboxes.get("sbx_merged")
        assert persisted is not None
        assert persisted.status is SandboxStatus.MERGED

    def test_leaves_cleaned_unchanged_even_if_directory_missing(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        row = seed_sandbox(
            self.db.sandboxes,
            sandbox_id="sbx_cleaned",
            create_dir=False,
        )
        self.db.sandboxes.update_status(row.id, SandboxStatus.CLEANED)

        result = collect_sandbox_show(git_fs.base_path, self.db.sandboxes, "sbx_cleaned")
        assert result.status is SandboxShowStatus.OK
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.status is SandboxStatus.CLEANED
        assert not result.disk_present
        assert not result.reconciled

        persisted = self.db.sandboxes.get("sbx_cleaned")
        assert persisted is not None
        assert persisted.status is SandboxStatus.CLEANED

    def test_leaves_conflict_unchanged_even_if_directory_missing(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        row = seed_sandbox(
            self.db.sandboxes,
            sandbox_id="sbx_conflict",
            create_dir=False,
        )
        self.db.sandboxes.update_status(row.id, SandboxStatus.CONFLICT)

        result = collect_sandbox_show(git_fs.base_path, self.db.sandboxes, "sbx_conflict")
        assert result.status is SandboxShowStatus.OK
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.status is SandboxStatus.CONFLICT
        assert not result.disk_present
        assert not result.reconciled

        persisted = self.db.sandboxes.get("sbx_conflict")
        assert persisted is not None
        assert persisted.status is SandboxStatus.CONFLICT


class SandboxShowRenderTests:
    """Renderer unit tests using SandboxShowFormatter."""

    def test_detail_fields_order_and_values(self) -> None:
        sandbox = SandboxRecord(
            id="sbx_a1b2c3d4",
            name=None,
            branch_name="worktree/sandbox-sbx_a1b2c3d4",
            base_commit="4f2c9a1e8b3d6f0a2c5e7b1d9a3f6c8e0b2d4f6a",
            sandbox_path=Path(".worktree/sandboxes/sbx_a1b2c3d4"),
            status=SandboxStatus.ACTIVE,
            created_at="2026-08-03 10:00:00",
            updated_at="2026-08-03 10:00:00",
        )
        data = SandboxShowResult(status=SandboxShowStatus.OK, sandbox=sandbox, disk_present=True)
        formatter = SandboxShowFormatter()
        renderable = formatter.to_rich(data)
        out = render_rich(renderable, width=120)
        assert "sbx_a1b2c3d4" in out
        assert "worktree/sandbox-sbx_a1b2c3d4" in out
        assert "4f2c9a1e8b3d6f0a2c5e7b1d9a3f6c8e0b2d4f6a" in out
        assert ".worktree/sandboxes/sbx_a1b2c3d4" in out
        assert "active" in out
        assert "present" in out
        assert "2026-08-03 10:00:00" in out
        assert "-" in out
        assert "Note:" not in out

        labels = [
            "ID:",
            "Name:",
            "Branch:",
            "Base Commit:",
            "Path:",
            "Status:",
            "Disk:",
            "Created:",
            "Updated:",
        ]
        positions = [out.index(label) for label in labels]
        assert positions == sorted(positions)

    def test_reconciled_note(self) -> None:
        sandbox = SandboxRecord(
            id="sbx_gone",
            name="old",
            branch_name="worktree/sandbox-sbx_gone",
            base_commit="abc",
            sandbox_path=Path("/tmp/missing-sandbox"),
            status=SandboxStatus.CLEANED,
            created_at="2026-08-03 10:00:00",
            updated_at="2026-08-03 11:00:00",
        )
        data = SandboxShowResult(status=SandboxShowStatus.OK, sandbox=sandbox, disk_present=False, reconciled=True)
        formatter = SandboxShowFormatter()
        renderable = formatter.to_rich(data)
        out = render_rich(renderable)
        assert "cleaned" in out
        assert "missing" in out
        assert "Note: sandbox directory is missing; status updated to 'cleaned'." in out

    def test_not_found_panel(self) -> None:
        data = SandboxShowResult(status=SandboxShowStatus.NOT_FOUND, errors=["Sandbox 'sbx_missing' not found."])
        formatter = SandboxShowFormatter()
        renderable = formatter.to_rich(data)
        out = render_rich(renderable)
        assert "Sandbox Not Found" in out
        assert "Sandbox 'sbx_missing' not found." in out
        assert "wt sandbox list" in out


class SandboxShowCommandDirectTests:
    """Direct sandbox_show_command exit-code / side-effect tests."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path, db_rel_path=DB_REL)

    def test_not_found_exits_one(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_show_command(ctx, "sbx_missing")
        assert not outcome.ok
        out = capsys.readouterr().out
        assert "Sandbox Not Found" in out

    def test_found_exits_zero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        created = seed_sandbox(self.db.sandboxes, sandbox_id="sbx_one", path_suffix="1")

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_show_command(ctx, created.id)
        assert outcome.ok
        out = capsys.readouterr().out
        assert created.id in out
        assert "active" in out
        assert "present" in out

    def test_reconcile_exits_zero_with_note(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        stale = seed_sandbox(
            self.db.sandboxes,
            sandbox_id="sbx_stale_cmd",
            path_suffix="gone-cmd",
            create_dir=False,
        )

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_show_command(ctx, stale.id)
        assert outcome.ok
        out = capsys.readouterr().out
        assert "cleaned" in out
        assert "missing" in out
        assert "Note: sandbox directory is missing; status updated to 'cleaned'." in out


class SandboxShowCliTests:
    """CliRunner coverage for Typer wiring."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, git_fs: GitFileSystem) -> None:
        self.db = WorktreeDb(path=git_fs.base_path, db_rel_path=DB_REL)

    def test_help_lists_show(self) -> None:
        result = runner.invoke(app, ["sandbox", "--help"])
        assert result.exit_code == 0

        sandbox_cmd = get_command(app).get_command(None, "sandbox")
        assert "show" in sandbox_cmd.list_commands(None)
        assert "list" in sandbox_cmd.list_commands(None)

    def test_show_help(self) -> None:
        result = runner.invoke(app, ["sandbox", "show", "--help"])
        assert result.exit_code == 0

        show_cmd = get_command(app).get_command(None, "sandbox").get_command(None, "show")
        assert show_cmd.help == "Show full detail for one tracked sandbox."
        assert any(param.name == "sandbox_id" for param in show_cmd.params)

    def test_show_via_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        created = seed_sandbox(
            self.db.sandboxes,
            sandbox_id="sbx_cli",
            name="cli-name",
            path_suffix="cli",
        )
        result = runner.invoke(app, ["sandbox", "show", created.id])
        assert result.exit_code == 0
        assert created.id in result.stdout
        assert "cli-name" in result.stdout
        assert "present" in result.stdout

    def test_show_via_cli_uninitialized(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        result = runner.invoke(app, ["sandbox", "show", "sbx_any"])
        assert result.exit_code == 1
        assert "Worktree workspace is not initialized." in result.stdout
