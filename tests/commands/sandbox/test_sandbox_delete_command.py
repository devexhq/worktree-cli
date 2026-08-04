"""Tests for `wt sandbox delete`."""

from __future__ import annotations

import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.sandbox.command import (
    collect_sandbox_delete,
    sandbox_delete_command,
)
from getworktree.commands.sandbox.models import SandboxDeleteStatus
from getworktree.commands.sandbox.renderers import (
    render_sandbox_already_cleaned,
    render_sandbox_delete_success,
    sandbox_delete_confirm_prompt,
)
from getworktree.common.utils import RichOutput
from getworktree.core.config.generator import generate_default_config
from getworktree.core.db import (
    SandboxStatus,
    get_sandbox,
    insert_sandbox,
    update_sandbox_status,
)
from getworktree.core.git_sandbox import GitSandboxManager

runner = CliRunner()
DB_REL = ".worktree/token_audit.db"


def _init_git_repo(path: Path, branch: str = "feature") -> None:
    subprocess.run(
        ["git", "init", "-b", branch], cwd=path, check=True, capture_output=True
    )
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


def _insert(
    repo: Path,
    *,
    sandbox_id: str,
    name: str | None = None,
    path_suffix: str | None = None,
    create_dir: bool = True,
    base_commit: str = "4f2c9a1e8b3d6f0a2c5e7b1d9a3f6c8e0b2d4f6a",
):
    suffix = path_suffix if path_suffix is not None else sandbox_id
    sandbox_path = repo / ".worktree" / "sandboxes" / suffix
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
    buffer = StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        color_system=None,
        width=width,
    )
    return RichOutput(console=console), buffer


class SandboxDeleteCollectTests:
    """Tests for collect_sandbox_delete (data path, no mutation)."""

    def test_not_initialized(self, git_repo: Path) -> None:
        result = collect_sandbox_delete("sbx_any", cwd=git_repo)
        assert result.status is SandboxDeleteStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert result.sandbox is None
        assert not (git_repo / DB_REL).exists()

    def test_invalid_config_is_not_initialized(self, git_repo: Path) -> None:
        config_path = git_repo / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{not-json", encoding="utf-8")

        result = collect_sandbox_delete("sbx_any", cwd=git_repo)
        assert result.status is SandboxDeleteStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert not (git_repo / DB_REL).exists()

    def test_not_found(self, git_repo: Path) -> None:
        _init_config(git_repo)
        result = collect_sandbox_delete("sbx_missing", cwd=git_repo)
        assert result.status is SandboxDeleteStatus.NOT_FOUND
        assert not result.ok
        assert result.sandbox is None

    def test_already_cleaned(self, git_repo: Path) -> None:
        _init_config(git_repo)
        created = _insert(
            git_repo,
            sandbox_id="sbx_clean",
            create_dir=False,
        )
        updated = update_sandbox_status(
            created.id,
            SandboxStatus.CLEANED,
            cwd=git_repo,
            db_rel_path=DB_REL,
        )
        assert updated is not None

        result = collect_sandbox_delete(created.id, cwd=git_repo)
        assert result.status is SandboxDeleteStatus.ALREADY_CLEANED
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.status is SandboxStatus.CLEANED

    @pytest.mark.parametrize(
        "status",
        [
            SandboxStatus.ACTIVE,
            SandboxStatus.MERGED,
            SandboxStatus.CONFLICT,
        ],
    )
    def test_ready_for_deletable_statuses(
        self,
        git_repo: Path,
        status: SandboxStatus,
    ) -> None:
        _init_config(git_repo)
        created = _insert(
            git_repo,
            sandbox_id=f"sbx_{status.value}",
            path_suffix=status.value,
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

        result = collect_sandbox_delete(created.id, cwd=git_repo)
        assert result.status is SandboxDeleteStatus.READY
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.status is status


class SandboxDeleteRenderTests:
    """Renderer unit tests with a fixed console width."""

    def test_already_cleaned_message(self) -> None:
        rich_output, buffer = _rich()
        render_sandbox_already_cleaned("sbx_done", rich_output=rich_output)
        out = buffer.getvalue()
        assert "Sandbox 'sbx_done' is already cleaned; nothing to remove." in out

    def test_delete_success(self) -> None:
        rich_output, buffer = _rich()
        render_sandbox_delete_success("sbx_gone", rich_output=rich_output)
        out = buffer.getvalue()
        assert "Sandbox deleted: sbx_gone" in out

    def test_confirm_prompt_text(self, git_repo: Path) -> None:
        _init_config(git_repo)
        row = _insert(git_repo, sandbox_id="sbx_prompt", name="demo")
        prompt = sandbox_delete_confirm_prompt(row)
        assert "Delete sandbox 'sbx_prompt'" in prompt
        assert f"branch {row.branch_name}" in prompt
        assert f"path {row.sandbox_path}" in prompt
        assert "This removes the git worktree and branch." in prompt


class SandboxDeleteCommandDirectTests:
    """Direct sandbox_delete_command exit-code / side-effect tests."""

    def test_not_initialized_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_delete_command("sbx_any", cwd=git_repo)
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
            sandbox_delete_command("sbx_missing", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        out = capsys.readouterr().out
        assert "Sandbox Not Found" in out
        assert "Sandbox 'sbx_missing' not found." in out

    def test_already_cleaned_noop(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        created = _insert(git_repo, sandbox_id="sbx_clean_cmd", create_dir=False)
        update_sandbox_status(
            created.id,
            SandboxStatus.CLEANED,
            cwd=git_repo,
            db_rel_path=DB_REL,
        )

        with (
            patch.object(GitSandboxManager, "cleanup_sandbox") as cleanup,
            patch("getworktree.commands.sandbox.command.typer.confirm") as confirm,
            pytest.raises(typer.Exit) as exc_info,
        ):
            sandbox_delete_command(created.id, cwd=git_repo)
        assert exc_info.value.exit_code == 0
        cleanup.assert_not_called()
        confirm.assert_not_called()
        out = capsys.readouterr().out
        assert f"Sandbox '{created.id}' is already cleaned; nothing to remove." in out

    def test_declined_confirm_aborts(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        created = _insert(git_repo, sandbox_id="sbx_decline")
        sandbox_path = Path(created.sandbox_path)

        with (
            patch.object(GitSandboxManager, "cleanup_sandbox") as cleanup,
            patch(
                "getworktree.commands.sandbox.command.typer.confirm",
                return_value=False,
            ) as confirm,
            pytest.raises(typer.Exit) as exc_info,
        ):
            sandbox_delete_command(created.id, cwd=git_repo)
        assert exc_info.value.exit_code == 1
        confirm.assert_called_once()
        cleanup.assert_not_called()
        assert sandbox_path.is_dir()
        loaded = get_sandbox(created.id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.ACTIVE
        assert "Aborted." in capsys.readouterr().out

    def test_eof_confirm_aborts(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        created = _insert(git_repo, sandbox_id="sbx_eof")

        with (
            patch.object(GitSandboxManager, "cleanup_sandbox") as cleanup,
            patch(
                "getworktree.commands.sandbox.command.typer.confirm",
                side_effect=typer.Abort(),
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            sandbox_delete_command(created.id, cwd=git_repo)
        assert exc_info.value.exit_code == 1
        cleanup.assert_not_called()
        loaded = get_sandbox(created.id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.ACTIVE
        assert "Aborted." in capsys.readouterr().out

    def test_force_skips_prompt_and_deletes(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        session = GitSandboxManager(cwd=git_repo).create_sandbox(name="force-me")
        assert Path(session.sandbox_path).is_dir()

        with (
            patch("getworktree.commands.sandbox.command.typer.confirm") as confirm,
            pytest.raises(typer.Exit) as exc_info,
        ):
            sandbox_delete_command(session.session_id, force=True, cwd=git_repo)
        assert exc_info.value.exit_code == 0
        confirm.assert_not_called()
        assert not Path(session.sandbox_path).exists()
        loaded = get_sandbox(session.session_id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED
        assert f"Sandbox deleted: {session.session_id}" in capsys.readouterr().out

    def test_confirmed_delete(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        session = GitSandboxManager(cwd=git_repo).create_sandbox()

        with (
            patch(
                "getworktree.commands.sandbox.command.typer.confirm",
                return_value=True,
            ) as confirm,
            pytest.raises(typer.Exit) as exc_info,
        ):
            sandbox_delete_command(session.session_id, cwd=git_repo)
        assert exc_info.value.exit_code == 0
        confirm.assert_called_once()
        assert not Path(session.sandbox_path).exists()
        loaded = get_sandbox(session.session_id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED
        assert f"Sandbox deleted: {session.session_id}" in capsys.readouterr().out

    def test_force_delete_missing_directory_still_succeeds(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        created = _insert(
            git_repo,
            sandbox_id="sbx_missing_dir",
            create_dir=False,
        )
        assert not Path(created.sandbox_path).exists()

        with pytest.raises(typer.Exit) as exc_info:
            sandbox_delete_command(created.id, force=True, cwd=git_repo)
        assert exc_info.value.exit_code == 0
        loaded = get_sandbox(created.id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED
        assert f"Sandbox deleted: {created.id}" in capsys.readouterr().out

    def test_cleanup_receives_session_from_row(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        created = _insert(
            git_repo,
            sandbox_id="sbx_session",
            name="named",
        )

        with (
            patch.object(GitSandboxManager, "cleanup_sandbox") as cleanup,
            pytest.raises(typer.Exit) as exc_info,
        ):
            sandbox_delete_command(created.id, force=True, cwd=git_repo)
        assert exc_info.value.exit_code == 0
        cleanup.assert_called_once()
        session = cleanup.call_args.args[0]
        assert session.session_id == created.id
        assert session.target_branch == created.branch_name
        assert session.sandbox_path == created.sandbox_path
        assert session.base_commit == created.base_commit
        assert session.name == created.name
        assert session.created_at == created.created_at


class SandboxDeleteCliTests:
    """CliRunner coverage for Typer wiring."""

    def test_help_lists_delete(self) -> None:
        result = runner.invoke(app, ["sandbox", "--help"])
        assert result.exit_code == 0

        sandbox_cmd = get_command(app).get_command(None, "sandbox")
        assert "delete" in sandbox_cmd.list_commands(None)
        assert "create" in sandbox_cmd.list_commands(None)
        assert "list" in sandbox_cmd.list_commands(None)
        assert "show" in sandbox_cmd.list_commands(None)

    def test_delete_help(self) -> None:
        result = runner.invoke(app, ["sandbox", "delete", "--help"])
        assert result.exit_code == 0

        delete_cmd = (
            get_command(app).get_command(None, "sandbox").get_command(None, "delete")
        )
        assert (
            delete_cmd.help
            == "Delete a sandbox worktree and branch after confirmation."
        )
        assert any(param.name == "sandbox_id" for param in delete_cmd.params)
        opts: set[str] = set()
        for param in delete_cmd.params:
            opts.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            opts.update(secondary)
        assert "--force" in opts

    def test_cli_force_delete(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        session = GitSandboxManager(cwd=git_repo).create_sandbox()

        result = runner.invoke(
            app,
            ["sandbox", "delete", session.session_id, "--force"],
        )
        assert result.exit_code == 0
        assert f"Sandbox deleted: {session.session_id}" in result.stdout
        loaded = get_sandbox(session.session_id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED

    def test_cli_declined_delete(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_config(git_repo)
        created = _insert(git_repo, sandbox_id="sbx_cli_no")

        result = runner.invoke(
            app,
            ["sandbox", "delete", created.id],
            input="n\n",
        )
        assert result.exit_code == 1
        assert "Aborted." in result.stdout
        loaded = get_sandbox(created.id, cwd=git_repo, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.ACTIVE
