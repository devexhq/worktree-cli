"""Tests for `wt sandbox delete`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.main import get_command
from typer.testing import CliRunner

from tests.helpers import GitFileSystem, make_rich_output, seed_sandbox
from worktree.cli import app
from worktree.cli.context import get_cli_context
from worktree.cli.sandbox.commands.sandbox_delete import (
    collect_sandbox_delete,
    sandbox_delete_command,
)
from worktree.cli.sandbox.models import SandboxDeleteStatus
from worktree.cli.sandbox.renderers import (
    render_sandbox_already_cleaned,
    render_sandbox_delete_success,
    sandbox_delete_confirm_prompt,
)
from worktree.core.db import (
    SandboxesRepository,
    SandboxStatus,
)
from worktree.core.git_sandbox import GitSandboxManager

runner = CliRunner()
DB_REL = ".worktree/data.db"


class SandboxDeleteCollectTests:
    """Tests for collect_sandbox_delete (data path, no mutation)."""

    def test_not_initialized(self, git_fs: GitFileSystem) -> None:
        result = collect_sandbox_delete("sbx_any", context=get_cli_context(cwd=git_fs.base_path))
        assert result.status is SandboxDeleteStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert result.sandbox is None
        assert not (git_fs.base_path / DB_REL).exists()

    def test_invalid_config_is_not_initialized(self, git_fs: GitFileSystem) -> None:
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{not-json", encoding="utf-8")

        result = collect_sandbox_delete("sbx_any", context=get_cli_context(cwd=git_fs.base_path))
        assert result.status is SandboxDeleteStatus.NOT_INITIALIZED
        assert not result.ok
        assert result.errors
        assert not (git_fs.base_path / DB_REL).exists()

    def test_not_found(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        result = collect_sandbox_delete("sbx_missing", context=get_cli_context(cwd=git_fs.base_path))
        assert result.status is SandboxDeleteStatus.NOT_FOUND
        assert not result.ok
        assert result.sandbox is None

    def test_already_cleaned(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        created = seed_sandbox(
            git_fs.base_path,
            sandbox_id="sbx_clean",
            create_dir=False,
        )
        updated = SandboxesRepository(git_fs.base_path, DB_REL).update_status(
            created.id,
            SandboxStatus.CLEANED,
        )
        assert updated is not None

        result = collect_sandbox_delete(created.id, context=get_cli_context(cwd=git_fs.base_path))
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
        git_fs: GitFileSystem,
        status: SandboxStatus,
    ) -> None:
        git_fs.init_repo()
        created = seed_sandbox(
            git_fs.base_path,
            sandbox_id=f"sbx_{status.value}",
            path_suffix=status.value,
        )
        if status is not SandboxStatus.ACTIVE:
            updated = SandboxesRepository(git_fs.base_path, DB_REL).update_status(
                created.id,
                status,
            )
            assert updated is not None
            created = updated

        result = collect_sandbox_delete(created.id, context=get_cli_context(cwd=git_fs.base_path))
        assert result.status is SandboxDeleteStatus.READY
        assert result.ok
        assert result.sandbox is not None
        assert result.sandbox.status is status


class SandboxDeleteRenderTests:
    """Renderer unit tests with a fixed console width."""

    def test_already_cleaned_message(self) -> None:
        rich_output, buffer = make_rich_output()
        render_sandbox_already_cleaned("sbx_done", output=rich_output)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox 'sbx_done' is already cleaned; nothing to remove." in out

    def test_delete_success(self) -> None:
        rich_output, buffer = make_rich_output()
        render_sandbox_delete_success("sbx_gone", output=rich_output)
        rich_output.print()
        out = buffer.getvalue()
        assert "Sandbox deleted: sbx_gone" in out

    def test_confirm_prompt_text(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        row = seed_sandbox(git_fs.base_path, sandbox_id="sbx_prompt", name="demo")
        prompt = sandbox_delete_confirm_prompt(row)
        assert "Delete sandbox 'sbx_prompt'" in prompt
        assert f"branch {row.branch_name}" in prompt
        assert f"path {row.sandbox_path}" in prompt
        assert "This removes the git worktree and branch." in prompt


class SandboxDeleteCommandDirectTests:
    """Direct sandbox_delete_command exit-code / side-effect tests."""

    def test_not_initialized_exits_one(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        ctx = get_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_delete_command("sbx_any", context=ctx)
        assert not outcome.ok
        ctx.output.print()

        out = capsys.readouterr().out
        assert "Worktree Not Initialized" in out
        assert not (git_fs.base_path / DB_REL).exists()

    def test_not_found_exits_one(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        ctx = get_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_delete_command("sbx_missing", context=ctx)
        assert not outcome.ok
        ctx.output.print()
        out = capsys.readouterr().out
        assert "Sandbox Not Found" in out
        assert "Sandbox 'sbx_missing' not found." in out

    def test_already_cleaned_noop(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        created = seed_sandbox(git_fs.base_path, sandbox_id="sbx_clean_cmd", create_dir=False)
        SandboxesRepository(git_fs.base_path, DB_REL).update_status(
            created.id,
            SandboxStatus.CLEANED,
        )

        with (
            patch.object(GitSandboxManager, "cleanup_sandbox") as cleanup,
            patch("worktree.cli.sandbox.commands.sandbox_delete.typer.confirm") as confirm,
        ):
            ctx = get_cli_context(cwd=git_fs.base_path)
            outcome = sandbox_delete_command(created.id, context=ctx)
        assert outcome.ok
        ctx.output.print()
        cleanup.assert_not_called()
        confirm.assert_not_called()
        out = capsys.readouterr().out
        assert f"Sandbox '{created.id}' is already cleaned; nothing to remove." in out

    def test_declined_confirm_aborts(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        created = seed_sandbox(git_fs.base_path, sandbox_id="sbx_decline")
        sandbox_path = Path(created.sandbox_path)

        with (
            patch.object(GitSandboxManager, "cleanup_sandbox") as cleanup,
            patch(
                "worktree.cli.sandbox.commands.sandbox_delete.typer.confirm",
                return_value=False,
            ) as confirm,
        ):
            ctx = get_cli_context(cwd=git_fs.base_path)
            outcome = sandbox_delete_command(created.id, context=ctx)
        assert not outcome.ok
        ctx.output.print()
        confirm.assert_called_once()
        cleanup.assert_not_called()
        assert sandbox_path.is_dir()
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(created.id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.ACTIVE
        assert "Aborted." in capsys.readouterr().out

    def test_eof_confirm_aborts(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        created = seed_sandbox(git_fs.base_path, sandbox_id="sbx_eof")

        with (
            patch.object(GitSandboxManager, "cleanup_sandbox") as cleanup,
            patch(
                "worktree.cli.sandbox.commands.sandbox_delete.typer.confirm",
                side_effect=typer.Abort(),
            ),
        ):
            ctx = get_cli_context(cwd=git_fs.base_path)
            outcome = sandbox_delete_command(created.id, context=ctx)
        assert not outcome.ok
        ctx.output.print()
        cleanup.assert_not_called()
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(created.id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.ACTIVE
        assert "Aborted." in capsys.readouterr().out

    def test_force_skips_prompt_and_deletes(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        session = GitSandboxManager(path=git_fs.base_path).create_sandbox(name="force-me")
        assert Path(session.sandbox_path).is_dir()

        with (
            patch("worktree.cli.sandbox.commands.sandbox_delete.typer.confirm") as confirm,
        ):
            ctx = get_cli_context(cwd=git_fs.base_path)
            outcome = sandbox_delete_command(session.session_id, force=True, context=ctx)
        assert outcome.ok
        ctx.output.print()
        confirm.assert_not_called()
        assert not Path(session.sandbox_path).exists()
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(session.session_id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED
        assert f"Sandbox deleted: {session.session_id}" in capsys.readouterr().out

    def test_confirmed_delete(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        session = GitSandboxManager(path=git_fs.base_path).create_sandbox()

        with (
            patch(
                "worktree.cli.sandbox.commands.sandbox_delete.typer.confirm",
                return_value=True,
            ) as confirm,
        ):
            ctx = get_cli_context(cwd=git_fs.base_path)
            outcome = sandbox_delete_command(session.session_id, context=ctx)

        assert outcome.ok
        ctx.output.print()
        confirm.assert_called_once()
        assert not Path(session.sandbox_path).exists()
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(session.session_id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED
        assert f"Sandbox deleted: {session.session_id}" in capsys.readouterr().out

    def test_force_delete_missing_directory_still_succeeds(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        created = seed_sandbox(
            git_fs.base_path,
            sandbox_id="sbx_missing_dir",
            create_dir=False,
        )
        assert not Path(created.sandbox_path).exists()

        ctx = get_cli_context(cwd=git_fs.base_path)
        outcome = sandbox_delete_command(created.id, force=True, context=ctx)
        assert outcome.ok
        ctx.output.print()
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(created.id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED
        assert f"Sandbox deleted: {created.id}" in capsys.readouterr().out

    def test_cleanup_receives_session_from_row(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        created = seed_sandbox(
            git_fs.base_path,
            sandbox_id="sbx_session",
            name="named",
        )

        with (
            patch.object(GitSandboxManager, "cleanup_sandbox") as cleanup,
        ):
            ctx = get_cli_context(cwd=git_fs.base_path)
            outcome = sandbox_delete_command(created.id, force=True, context=ctx)
        assert outcome.ok
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

        delete_cmd = get_command(app).get_command(None, "sandbox").get_command(None, "delete")
        assert delete_cmd.help == "Delete a sandbox worktree and branch after confirmation."
        assert any(param.name == "sandbox_id" for param in delete_cmd.params)
        opts: set[str] = set()
        for param in delete_cmd.params:
            opts.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            opts.update(secondary)
        assert "--force" in opts

    def test_cli_force_delete(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        session = GitSandboxManager(path=git_fs.base_path).create_sandbox()

        result = runner.invoke(
            app,
            ["sandbox", "delete", session.session_id, "--force"],
        )
        assert result.exit_code == 0
        assert f"Sandbox deleted: {session.session_id}" in result.stdout
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(session.session_id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.CLEANED

    def test_cli_declined_delete(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        created = seed_sandbox(git_fs.base_path, sandbox_id="sbx_cli_no")

        result = runner.invoke(
            app,
            ["sandbox", "delete", created.id],
            input="n\n",
        )
        assert result.exit_code == 1
        assert "Aborted." in result.stdout
        loaded = SandboxesRepository(git_fs.base_path, DB_REL).get(created.id)
        assert loaded is not None
        assert loaded.status is SandboxStatus.ACTIVE
