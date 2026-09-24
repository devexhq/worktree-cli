"""Single-tier CLI integration tests for wt run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.harness.catalog import write_runnable_blueprint
from worktree.cli import app
from worktree.cli.ui.dispatcher import UiDispatcher
from worktree.core.db import RunStatus, WorktreeDb


def _raise_keyboard_interrupt(*_args: object, **_kwargs: object) -> str:
    """Stand in for builtins.input, simulating a Ctrl+C during a blocking prompt read."""
    raise KeyboardInterrupt


def _force_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force UiDispatcher.is_interactive True so DispatcherFailurePrompter reads stdin.

    Console().is_terminal is always False under CliRunner.invoke (stdout is not a real
    TTY), so the prompter's interactivity gate must be forced open to exercise its
    blocking input() call from a CLI integration test.
    """
    monkeypatch.setattr(UiDispatcher, "is_interactive", property(lambda self: True))


class RunCliIntegrationTests:
    """Typer runner integration tests for wt run."""

    def test_run_cli_no_sandbox_completes_in_place_exits_zero(self, cli_runner: CliRunner, run_workspace: Path) -> None:
        """wt run --no-sandbox: single-step blueprint completes in place, exit 0, 'Sandbox: In-place (workspace)' in stdout."""
        write_runnable_blueprint(run_workspace, key="noop-task", steps=[{"id": "s1", "run": "true"}])

        result = cli_runner.invoke(app, ["-p", str(run_workspace), "run", "noop-task", "--no-sandbox"])

        assert result.exit_code == 0
        assert "Blueprint Run Completed:" in result.stdout
        assert "Sandbox: In-place (workspace)" in result.stdout

    def test_run_cli_sandbox_enabled_completes_in_active_worktree_exits_zero(
        self, cli_runner: CliRunner, run_workspace: Path
    ) -> None:
        """wt run (sandbox default on): single-step blueprint completes, exit 0, 'Sandbox: Active (' in stdout."""
        write_runnable_blueprint(run_workspace, key="sandboxed-task", steps=[{"id": "s1", "run": "true"}])

        result = cli_runner.invoke(app, ["-p", str(run_workspace), "run", "sandboxed-task"])

        assert result.exit_code == 0
        assert "Sandbox: Active (" in result.stdout

    def test_run_cli_prompt_user_retry_then_succeeds_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, cli_runner: CliRunner, run_workspace: Path
    ) -> None:
        """wt run: on_failure=prompt_user step fed input='r\\n' retries and completes, exit 0."""
        _force_interactive(monkeypatch)
        write_runnable_blueprint(
            run_workspace,
            key="retry-task",
            steps=[
                {
                    "id": "s1",
                    "run": "test -f marker.txt && exit 0 || (touch marker.txt && exit 1)",
                    "on_failure": "prompt_user",
                }
            ],
        )

        result = cli_runner.invoke(app, ["-p", str(run_workspace), "run", "retry-task", "--no-sandbox"], input="r\n")

        assert result.exit_code == 0
        assert "Blueprint Run Completed:" in result.stdout

    def test_run_cli_prompt_user_abort_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, cli_runner: CliRunner, run_workspace: Path
    ) -> None:
        """wt run: on_failure=prompt_user step fed input='a\\n' aborts the run, exit 1."""
        _force_interactive(monkeypatch)
        write_runnable_blueprint(
            run_workspace,
            key="abort-task",
            steps=[{"id": "s1", "run": "exit 1", "on_failure": "prompt_user"}],
        )

        result = cli_runner.invoke(app, ["-p", str(run_workspace), "run", "abort-task", "--no-sandbox"], input="a\n")

        assert result.exit_code == 1
        assert "Run Failed" in result.stdout

    def test_run_cli_prompt_user_continue_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, cli_runner: CliRunner, run_workspace: Path
    ) -> None:
        """wt run: on_failure=prompt_user step fed input='c\\n' ignores the failure and completes, exit 0."""
        _force_interactive(monkeypatch)
        write_runnable_blueprint(
            run_workspace,
            key="continue-task",
            steps=[
                {"id": "s1", "run": "exit 1", "on_failure": "prompt_user"},
                {"id": "s2", "run": "true"},
            ],
        )

        result = cli_runner.invoke(app, ["-p", str(run_workspace), "run", "continue-task", "--no-sandbox"], input="c\n")

        assert result.exit_code == 0
        assert "Blueprint Run Completed:" in result.stdout

    def test_run_cli_prompt_user_keyboard_interrupt_persists_paused_checkpoint(
        self, monkeypatch: pytest.MonkeyPatch, cli_runner: CliRunner, run_workspace: Path
    ) -> None:
        """wt run: a KeyboardInterrupt raised from the interactive prompter after the checkpoint is saved sets the run record's status to PAUSED.

        🚨 Plan deviation: the plan's Instructions/Edge cases assert `--no-tty` on a
        prompt_user step reaches RunStatus.PAUSED and exits 0. Ground truth contradicts
        this on two points: (1) `_prompt_user_decision` in
        worktree/core/runtime/engine.py short-circuits to ABORT *before* the prompter is
        ever called whenever `context.no_tty` is True, so `--no-tty` can never reach the
        PromptUserInterruptedError/PAUSED path; PAUSED is only reachable via a
        KeyboardInterrupt raised *from inside* an interactive prompter call. (2) Even on
        that real path, `_run_step_loop` sets `errors=[str(exc)]` from the checkpoint's
        (always non-empty) diagnostic, so `BlueprintRunResult.ok` is False and
        `run_callback` raises `typer.Exit(code=1)` — a paused run can never exit 0 through
        this CLI path as currently implemented. This test exercises the real PAUSED
        mechanism (forced interactivity + input() raising KeyboardInterrupt) and pins the
        actual exit-1-with-PAUSED-record contract instead of the plan's unreachable one.
        """
        _force_interactive(monkeypatch)
        monkeypatch.setattr("builtins.input", _raise_keyboard_interrupt)
        write_runnable_blueprint(
            run_workspace,
            key="pause-task",
            steps=[{"id": "pause-step", "run": "exit 1", "on_failure": "prompt_user"}],
        )

        result = cli_runner.invoke(
            app,
            ["-p", str(run_workspace), "run", "pause-task", "--no-sandbox", "--session-id", "paused-session-1"],
        )

        assert result.exit_code == 1
        record = WorktreeDb(path=run_workspace).runs.get("paused-session-1")
        assert record is not None
        assert record.status == RunStatus.PAUSED

    def test_run_cli_json_format_emits_run_success_event(self, cli_runner: CliRunner, run_workspace: Path) -> None:
        """wt run --format json: NDJSON stream includes a RunSuccessEvent with payload.status == 'completed'."""
        write_runnable_blueprint(run_workspace, key="json-task", steps=[{"id": "s1", "run": "true"}])

        result = cli_runner.invoke(
            app, ["-p", str(run_workspace), "run", "json-task", "--no-sandbox", "--format", "json"]
        )

        assert result.exit_code == 0
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        success_events = [e for e in events if e["event_type"] == "RunSuccessEvent"]
        assert len(success_events) == 1
        assert success_events[0]["payload"]["status"] == "completed"

    def test_run_cli_uninitialized_git_repo_auto_initializes_and_proceeds(
        self, cli_runner: CliRunner, git_repo: Path
    ) -> None:
        """wt run: git repo with no .worktree/ auto-initializes (project.json + config.json written) instead of raising ConfigLoadError."""
        result = cli_runner.invoke(app, ["-p", str(git_repo), "run", "missing-workflow", "--no-sandbox"])

        assert "CONFIG_NOT_FOUND" not in result.stdout
        assert (git_repo / ".worktree" / "project.json").exists()
        assert (git_repo / ".worktree" / "config.json").exists()
