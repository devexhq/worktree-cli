"""Tests for `wt sandbox show`."""

from __future__ import annotations

import subprocess
from io import StringIO
from pathlib import Path

import pytest
import typer
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.cli.sandbox.command import (
    collect_sandbox_show,
    sandbox_show_command,
)
from getworktree.cli.sandbox.models import SandboxShowStatus
from getworktree.cli.sandbox.renderers import (
    build_sandbox_detail_table,
    render_sandbox_not_found,
    render_sandbox_show,
)
from getworktree.common.utils import RichOutput
from getworktree.core.config.generator import generate_default_config
from getworktree.core.db import (
    SandboxRecord,
    SandboxStatus,
    get_sandbox,
    insert_sandbox,
    update_sandbox_status,
)

runner = CliRunner()
DB_REL = ".worktree/data.db"


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
    base_commit: str = "4f2c9a1e8b3d6f0a2c5e7b1d9a3f6c8e0b2d4f6a",
):
    sandbox_path = repo / ".worktree" / "sandboxes" / path_suffix
    if create_dir:
        sandbox_path.mkdir(parents=True, exist_ok=True)
    return insert_sandbox(
        id=sandbox_id,
        branch_name=f"worktree/sandbox-{sandbox_id}",
        base_commit=base_commit,
        sandbox_path=sandbox_path,
        name=name,
        cwd=repo,
        db_rel_path=DB_REL,
    )


def _rich(*, width: int = 120) -> tuple[RichOutput, StringIO]:
    """Fixed-width console so Rich layout does not depend on CI COLUMNS."""
    buffer = StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        color_system=None,
        width=width,
    )
    return RichOutput(console=console), buffer


class SandboxShowCollectTests:
    """Tests for collect_sandbox_show (data path, no Rich width coupling)."""

    def test_not_initialized(self, git_repo: Path) -> None:
        result = collect_sandbox_show("sbx_any", cwd=git_repo)
        assert result.status is SandboxShowStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert result.sandbox is None
        assert not (git_repo / DB_REL).exists()

    def test_invalid_config_is_not_initialized(self, git_repo: Path) -> None:
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{not-json", encoding="utf-8")

        result = collect_sandbox_show("sbx_any", cwd=git_repo)
        assert result.status is SandboxShowStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert not (git_repo / DB_REL).exists()

    def test_not_found(self, git_repo: Path) -> None:
        _init_config(git_repo)
        result = collect_sandbox_show("sbx_missing", cwd=git_repo)
        assert result.status is SandboxShowStatus.NOT_FOUND
        assert not result.ok
        assert result.sandbox is None

    @pytest.mark.parametrize(
        ("status", "create_dir"),
        [
            (SandboxStatus.ACTIVE, True),
            (SandboxStatus.MERGED, True),
            (SandboxStatus.CLEANED, False),
            (SandboxStatus.CONFLICT, True),
        ],
    )
    def test_found_each_status(
        self,
        git_repo: Path,
        status: SandboxStatus,
        create_dir: bool,
    ) -> None:
        _init_config(git_repo)
        created = _insert(
            git_repo,
            sandbox_id=f"sbx_{status.value}",
            name="detail" if status is SandboxStatus.ACTIVE else None,
            path_suffix=status.value,
            create_dir=create_dir,
        )
        if status is not SandboxStatus.ACTIVE:
            updated = update_sandbox_status(
                created.id,
                status,
                cwd=git_repo,
                db_rel_path=DB_REL,
            )
            assert updated is not None
            created = updated

        result = collect_sandbox_show(created.id, cwd=git_repo)
        assert result.status is SandboxShowStatus.OK
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.id == created.id
        assert result.sandbox.status is status
        assert result.reconciled is False
        assert result.disk_present is create_dir

    def test_reconciles_stale_active_missing_directory(self, git_repo: Path) -> None:
        _init_config(git_repo)
        stale = _insert(
            git_repo,
            sandbox_id="sbx_stale",
            path_suffix="gone",
            create_dir=False,
        )
        assert not Path(stale.sandbox_path).exists()

        result = collect_sandbox_show(stale.id, cwd=git_repo)
        assert result.status is SandboxShowStatus.OK
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.status is SandboxStatus.CLEANED
        assert result.reconciled is True
        assert result.disk_present is False
        loaded = get_sandbox(stale.id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED

    def test_non_active_missing_dir_does_not_reconcile(self, git_repo: Path) -> None:
        _init_config(git_repo)
        created = _insert(
            git_repo,
            sandbox_id="sbx_merged_gone",
            path_suffix="merged-gone",
            create_dir=False,
        )
        update_sandbox_status(
            created.id,
            SandboxStatus.MERGED,
            cwd=git_repo,
            db_rel_path=DB_REL,
        )

        result = collect_sandbox_show(created.id, cwd=git_repo)
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.status is SandboxStatus.MERGED
        assert result.reconciled is False
        assert result.disk_present is False


class SandboxShowRenderTests:
    """Renderer unit tests with a fixed console width."""

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
        rich_output, buffer = _rich(width=120)
        render_sandbox_show(sandbox, disk_present=True, rich_output=rich_output)
        out = buffer.getvalue()
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

        table = build_sandbox_detail_table(sandbox, disk_present=True)
        assert len(table.rows) == 9

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
        rich_output, buffer = _rich()
        render_sandbox_show(
            sandbox,
            disk_present=False,
            reconciled=True,
            rich_output=rich_output,
        )
        out = buffer.getvalue()
        assert "cleaned" in out
        assert "missing" in out
        assert "Note: sandbox directory is missing; status updated to 'cleaned'." in out

    def test_not_found_panel(self) -> None:
        rich_output, buffer = _rich()
        render_sandbox_not_found("sbx_missing", rich_output=rich_output)
        out = buffer.getvalue()
        assert "Sandbox Not Found" in out
        assert "Sandbox 'sbx_missing' not found." in out
        assert "wt sandbox list" in out


class SandboxShowCommandDirectTests:
    """Direct sandbox_show_command exit-code / side-effect tests."""

    def test_not_initialized_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_show_command("sbx_any", cwd=git_repo)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Worktree Not Initialized" in out
        assert not (git_repo / DB_REL).exists()

    def test_not_found_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_show_command("sbx_missing", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        out = capsys.readouterr().out
        assert "Sandbox Not Found" in out

    def test_found_exits_zero(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        created = _insert(git_repo, sandbox_id="sbx_one", path_suffix="1")

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_show_command(created.id, cwd=git_repo)
        assert exc_info.value.exit_code == 0
        out = capsys.readouterr().out
        assert created.id in out
        assert "active" in out
        assert "present" in out

    def test_reconcile_exits_zero_with_note(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        stale = _insert(
            git_repo,
            sandbox_id="sbx_stale_cmd",
            path_suffix="gone-cmd",
            create_dir=False,
        )

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_show_command(stale.id, cwd=git_repo)
        assert exc_info.value.exit_code == 0
        out = capsys.readouterr().out
        assert "cleaned" in out
        assert "missing" in out
        assert "Note: sandbox directory is missing; status updated to 'cleaned'." in out


class SandboxShowCliTests:
    """CliRunner coverage for Typer wiring."""

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

    def test_show_via_cli(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        created = _insert(
            git_repo,
            sandbox_id="sbx_cli",
            name="cli-name",
            path_suffix="cli",
        )
        result = runner.invoke(app, ["sandbox", "show", created.id])
        assert result.exit_code == 0
        assert created.id in result.stdout
        assert "cli-name" in result.stdout
        assert "present" in result.stdout
