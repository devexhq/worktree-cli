"""Single-tier CLI smoke and crash-protection tests for the wt entrypoint."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import worktree.cli.cli as cli_module
from worktree.cli import app
from worktree.common.lock import LockTimeoutError


class CliSmokeTests:
    """Smoke tests for top-level wt CLI behavior."""

    def test_cli_bare_invocation_prints_banner_and_help_exits_zero(self, cli_runner: CliRunner) -> None:
        """wt (bare invocation): exit 0, 'Worktree CLI' and 'init' in stdout."""
        result = cli_runner.invoke(app, [])

        assert result.exit_code == 0
        assert "Worktree CLI" in result.stdout
        assert "init" in result.stdout


class RunCliCrashProtectionTests:
    """Direct tests for run_cli()'s top-level exception-to-panel mapping."""

    def test_run_cli_lock_timeout_renders_error_panel_and_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """run_cli(): app() raising LockTimeoutError renders a 'Workspace Lock Timeout' panel and exits via SystemExit(1)."""

        def _raise_lock_timeout() -> None:
            raise LockTimeoutError("lock held by another process")

        monkeypatch.setattr(cli_module, "app", _raise_lock_timeout)

        with pytest.raises(SystemExit) as exc_info:
            cli_module.run_cli()

        assert exc_info.value.code == 1
        assert "Workspace Lock Timeout" in capsys.readouterr().out

    def test_run_cli_unexpected_exception_renders_fatal_panel_and_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """run_cli(): app() raising a bare Exception renders a 'Fatal Error' panel and exits via SystemExit(1)."""

        def _raise_unexpected() -> None:
            raise RuntimeError("missing record.id")

        monkeypatch.setattr(cli_module, "app", _raise_unexpected)

        with pytest.raises(SystemExit) as exc_info:
            cli_module.run_cli()

        assert exc_info.value.code == 1
        assert "Fatal Error" in capsys.readouterr().out
