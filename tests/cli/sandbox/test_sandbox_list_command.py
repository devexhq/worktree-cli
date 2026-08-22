"""Tests for `wt sandbox list`."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
import typer
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli import app
from worktree.cli.sandbox.command import (
    collect_sandbox_list,
    sandbox_list_command,
)
from worktree.cli.sandbox.models import SandboxListStatus
from worktree.cli.sandbox.renderers import (
    build_sandbox_table,
    render_not_initialized,
    render_sandbox_list,
)
from worktree.common.utils import RichOutput
from worktree.core.db import (
    SandboxesRepository,
    SandboxRecord,
    SandboxStatus,
)

runner = CliRunner()
DB_REL = ".worktree/data.db"


def _insert(
    repo: Path,
    *,
    sandbox_id: str,
    name: str | None = None,
    path_suffix: str = "s",
    create_dir: bool = True,
):
    sandbox_path = repo / ".worktree" / "sandboxes" / path_suffix
    if create_dir:
        sandbox_path.mkdir(parents=True, exist_ok=True)
    return SandboxesRepository(repo, DB_REL).insert(
        id=sandbox_id,
        branch_name=f"worktree/sandbox-{sandbox_id}",
        base_commit="abc123",
        sandbox_path=sandbox_path,
        name=name,
    )


def _rich(*, width: int = 120) -> tuple[RichOutput, StringIO]:
    """Fixed-width console so Rich tables do not truncate under narrow CI COLUMNS."""
    buffer = StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        color_system=None,
        width=width,
    )
    return RichOutput(console=console), buffer


class SandboxListCollectTests:
    """Tests for collect_sandbox_list (data path, no Rich width coupling)."""

    def test_not_initialized(self, git_fs: GitFileSystem) -> None:
        result = collect_sandbox_list(cwd=git_fs.base_path)
        assert result.status is SandboxListStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert not (git_fs.base_path / DB_REL).exists()

    def test_empty_state(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        result = collect_sandbox_list(cwd=git_fs.base_path)
        assert result.status is SandboxListStatus.OK
        assert result.ok
        assert result.sandboxes == []

    def test_multiple_rows_sorted_by_created_at_desc(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        first = _insert(git_fs.base_path, sandbox_id="sbx_first", name=None, path_suffix="1")
        second = _insert(git_fs.base_path, sandbox_id="sbx_second", name="beta", path_suffix="2")
        db = SandboxesRepository(cwd=git_fs.base_path)
        import sqlite3

        with sqlite3.connect(db.db_path) as conn:
            conn.execute("UPDATE sandboxes SET created_at = '2026-01-01 00:00:00' WHERE id = ?", (first.id,))
            conn.execute("UPDATE sandboxes SET created_at = '2026-01-01 00:00:01' WHERE id = ?", (second.id,))
            conn.commit()
        first = db.get(first.id)
        second = db.get(second.id)

        result = collect_sandbox_list(cwd=git_fs.base_path)
        assert result.ok
        assert [row.id for row in result.sandboxes] == [second.id, first.id]
        assert result.sandboxes[0].name == "beta"
        assert result.sandboxes[1].name is None
        assert result.sandboxes[0].created_at == second.created_at
        assert result.sandboxes[1].created_at == first.created_at

    def test_status_filter(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        active = _insert(git_fs.base_path, sandbox_id="sbx_active", path_suffix="a")
        cleaned = _insert(git_fs.base_path, sandbox_id="sbx_cleaned", path_suffix="c")
        SandboxesRepository(git_fs.base_path, DB_REL).update_status(
            cleaned.id,
            SandboxStatus.CLEANED,
        )

        result = collect_sandbox_list(status="cleaned", cwd=git_fs.base_path)
        assert result.ok
        assert [row.id for row in result.sandboxes] == [cleaned.id]
        assert active.id not in {row.id for row in result.sandboxes}

    def test_reconciles_stale_active_missing_directory(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        stale = _insert(
            git_fs.base_path,
            sandbox_id="sbx_stale",
            path_suffix="gone",
            create_dir=False,
        )
        assert not Path(stale.sandbox_path).exists()

        result = collect_sandbox_list(cwd=git_fs.base_path)
        assert result.ok
        assert len(result.sandboxes) == 1
        assert result.sandboxes[0].id == stale.id
        assert result.sandboxes[0].status is SandboxStatus.CLEANED
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(stale.id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED

    def test_status_filter_after_reconciliation(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        stale = _insert(
            git_fs.base_path,
            sandbox_id="sbx_stale_filter",
            path_suffix="missing",
            create_dir=False,
        )

        result = collect_sandbox_list(status="active", cwd=git_fs.base_path)
        assert result.ok
        assert result.sandboxes == []
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(stale.id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED

    def test_collect_invalid_config_is_not_initialized(self, git_fs: GitFileSystem) -> None:
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{not-json", encoding="utf-8")

        result = collect_sandbox_list(cwd=git_fs.base_path)
        assert result.status is SandboxListStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert not (git_fs.base_path / DB_REL).exists()


class SandboxListRenderTests:
    """Renderer unit tests with a fixed console width."""

    def test_table_columns_and_rows(self) -> None:
        sandboxes = [
            SandboxRecord(
                id="sbx_second",
                name="beta",
                branch_name="worktree/sandbox-sbx_second",
                base_commit="abc",
                sandbox_path=Path("/tmp/b"),
                status=SandboxStatus.ACTIVE,
                created_at="2026-01-02 00:00:00",
                updated_at="2026-01-02 00:00:00",
            ),
            SandboxRecord(
                id="sbx_first",
                name=None,
                branch_name="worktree/sandbox-sbx_first",
                base_commit="abc",
                sandbox_path=Path("/tmp/a"),
                status=SandboxStatus.ACTIVE,
                created_at="2026-01-01 00:00:00",
                updated_at="2026-01-01 00:00:00",
            ),
        ]
        rich_output, buffer = _rich(width=120)
        render_sandbox_list(sandboxes, rich_output=rich_output)
        out = buffer.getvalue()
        assert "Worktree Sandboxes" in out
        for header in ("ID", "Name", "Branch", "Status", "Created"):
            assert header in out
        assert out.index("sbx_second") < out.index("sbx_first")
        assert "beta" in out
        assert "-" in out
        assert "2026-01-02 00:00:00" in out
        assert "2026-01-01 00:00:00" in out

        table = build_sandbox_table(sandboxes)
        assert [col.header for col in table.columns] == [
            "ID",
            "Name",
            "Branch",
            "Status",
            "Created",
        ]

    def test_empty_list_message(self) -> None:
        rich_output, buffer = _rich()
        render_sandbox_list([], rich_output=rich_output)
        assert buffer.getvalue() == "No sandboxes found.\n"

    def test_not_initialized_panel(self) -> None:
        rich_output, buffer = _rich()
        render_not_initialized(
            ["Configuration file not found at '/x' (CONFIG_NOT_FOUND)."],
            rich_output=rich_output,
        )
        out = buffer.getvalue()
        assert "Worktree Not Initialized" in out
        assert "CONFIG_NOT_FOUND" in out


class SandboxListCommandDirectTests:
    """Direct sandbox_list_command exit-code / side-effect tests."""

    def test_not_initialized_exits_one(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 1

        out = capsys.readouterr().out
        assert "Worktree Not Initialized" in out
        assert not (git_fs.base_path / DB_REL).exists()

    def test_empty_state_exits_zero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 0
        assert "No sandboxes found." in capsys.readouterr().out

    def test_populated_exits_zero(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        _insert(git_fs.base_path, sandbox_id="sbx_one", path_suffix="1")

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_list_command(cwd=git_fs.base_path)
        assert exc_info.value.exit_code == 0
        assert "Worktree Sandboxes" in capsys.readouterr().out


class SandboxListCliTests:
    """CliRunner coverage for Typer wiring."""

    def test_help_lists_sandbox_group(self) -> None:
        # Assert registration via Click metadata. Do not parse Rich --help text:
        # narrow CI terminals wrap/truncate option names and the docstring.
        result = runner.invoke(app, ["sandbox", "--help"])
        assert result.exit_code == 0

        sandbox_cmd = get_command(app).get_command(None, "sandbox")
        assert sandbox_cmd.help == "Inspect and manage git worktree sandboxes."
        assert "list" in sandbox_cmd.list_commands(None)

    def test_list_help(self) -> None:
        # Assert registration via Click metadata. Do not parse Rich --help text:
        # narrow CI terminals wrap/truncate option names and the docstring.
        result = runner.invoke(app, ["sandbox", "list", "--help"])
        assert result.exit_code == 0

        list_cmd = get_command(app).get_command(None, "sandbox").get_command(None, "list")
        assert list_cmd.help == "List tracked sandboxes and their lifecycle status."
        opts: set[str] = set()
        for param in list_cmd.params:
            opts.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            opts.update(secondary)
        assert "--status" in opts

    def test_invalid_status_rejected_by_typer(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        result = runner.invoke(app, ["sandbox", "list", "--status", "bogus"])
        assert result.exit_code != 0
        combined = result.stdout + result.stderr
        assert "bogus" in combined.lower() or "invalid" in combined.lower()

    def test_list_via_cli_empty(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        result = runner.invoke(app, ["sandbox", "list"])
        assert result.exit_code == 0
        assert "No sandboxes found." in result.stdout
