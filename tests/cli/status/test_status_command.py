"""Tests for the status command."""

from __future__ import annotations

import subprocess

import pytest

from tests.helpers import FileSystem, GitFileSystem, make_cli_context
from worktree.cli.status.commands.root import status_command


class StatusCommandTests:
    """Tests for status_command."""

    def test_status_with_config(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        subprocess.run(
            ["git", "checkout", "-b", "feature-cmd"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
        )
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        result = status_command(ctx)
        assert result.ok
        assert result.is_initialized

        out = capsys.readouterr().out
        assert "Worktree Workspace Status" in out
        assert git_fs.base_path.name in out
        assert "feature-cmd" in out

    def test_status_reconciles_stale_run(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        ctx.db.runs.create(
            session_id="sbx_status_stale",
            blueprint_name="my_task",
            kind="task",
            pid=9999999,
        )

        result = status_command(ctx)
        assert result.ok

        out = capsys.readouterr().out
        assert "Reconciled 1 interrupted session (session_id: sbx_status_stale)." in out
        assert "Worktree Workspace Status" in out

        # Re-query db to verify status became failed
        persisted = ctx.db.runs.get("sbx_status_stale")
        assert persisted is not None
        assert persisted.status.value == "failed"

    def test_status_without_init(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(fs.base_path)
        ctx = make_cli_context(cwd=fs.base_path)
        result = status_command(ctx)

        assert not result.is_initialized

        out = capsys.readouterr().out
        assert "Worktree Workspace Status" in out
        assert "Uninitialized" in out
        assert "CONFIG_NOT_FOUND" in out
        assert "Worktree workspace is not initialized" in out
        assert "Run 'wt init' to initialize Worktree in this repository." in out

    def test_status_with_broken_config_does_not_report_uninitialized(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        # Corrupt config by writing an incomplete JSON
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.write_text('{"version": 1, "project": {"name": "test-broken-proj"}}\n', encoding="utf-8")

        ctx = make_cli_context(cwd=git_fs.base_path)
        result = status_command(ctx)
        assert not result.ok
        assert result.is_initialized

        out = capsys.readouterr().out
        assert "Worktree Workspace Status (Degraded)" in out
        assert "test-broken-proj" in out
        assert "CONFIG_SCHEMA_INVALID" in out
        assert "Uninitialized" not in out

    def test_status_json_format(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        ctx = make_cli_context(cwd=git_fs.base_path)
        result = status_command(ctx, output_format="json")
        assert result.ok

        out = capsys.readouterr().out
        import json

        lines = [line for line in out.strip().split("\n") if line]
        assert len(lines) == 1
        envelope = json.loads(lines[0])
        assert envelope["event_type"] == "WorktreeStatusResult"
        assert envelope["payload"]["git"]["is_git_repo"] is True
        assert envelope["payload"]["config"]["status"] == "ok"


class StatusCliTests:
    """CliRunner coverage for `wt status`."""

    def test_status_help_includes_format_option(self) -> None:
        from typer.testing import CliRunner

        from tests.helpers import get_subcommand
        from worktree.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

        cmd = get_subcommand(app, "status")
        opts: set[str] = set()
        for param in cmd.params:
            opts.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            opts.update(secondary)
        assert "--format" in opts

    def test_status_cli_terminal(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner

        from worktree.cli import app

        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        runner = CliRunner()
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Worktree Workspace Status" in result.stdout

    def test_status_cli_json(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        import json

        from typer.testing import CliRunner

        from worktree.cli import app

        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()

        runner = CliRunner()
        result = runner.invoke(app, ["status", "--format", "json"])
        assert result.exit_code == 0
        lines = [line for line in result.stdout.strip().split("\n") if line]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["event_type"] == "WorktreeStatusResult"
        assert payload["payload"]["config"]["is_valid"] is True
