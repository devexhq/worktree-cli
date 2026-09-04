"""CLI smoke tests for the Typer entrypoint."""

from __future__ import annotations

import multiprocessing
import multiprocessing.synchronize
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli.cli import __version__, app

runner = CliRunner()


def _child_hold_lock_cli(target_dir: Path, ready: multiprocessing.synchronize.Event) -> None:
    from worktree.common.lock import WorkspaceLock

    with WorkspaceLock(target_dir, timeout_seconds=5.0):
        ready.set()
        time.sleep(0.6)


class CliSmokeTests:
    """Smoke tests for top-level CLI behavior."""

    def test_bare_invocation_prints_banner_and_help(self) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Worktree CLI" in result.stdout
        assert "init" in result.stdout

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Worktree CLI" in result.stdout
        assert __version__ in result.stdout

    def test_init_via_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (git_fs.base_path / ".worktree" / "config.json").is_file()
        assert (git_fs.base_path / ".worktree" / "data.db").is_file()

    def test_legacy_task_and_workflow_commands_unrecognized(self) -> None:
        result_task = runner.invoke(app, ["task"])
        assert result_task.exit_code == 2
        assert "No such command 'task'" in result_task.output

        result_workflow = runner.invoke(app, ["workflow"])
        assert result_workflow.exit_code == 2
        assert "No such command 'workflow'" in result_workflow.output

    def test_cli_lock_contention_displays_waiting_panel(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        runner.invoke(app, ["init"])

        ctx = multiprocessing.get_context("spawn")
        ready_event = ctx.Event()

        p = ctx.Process(target=_child_hold_lock_cli, args=(git_fs.base_path, ready_event))
        p.start()
        try:
            assert ready_event.wait(timeout=5.0), "Holder failed to acquire lock"

            result = runner.invoke(app, ["catalog", "list"])
            assert result.exit_code == 0
            assert "Lock Held" in result.output
            assert "Waiting for lock release" in result.output
        finally:
            p.join(timeout=5.0)
