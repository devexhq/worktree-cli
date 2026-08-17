"""Comprehensive CLI unit tests for task execution (wt task run)."""

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem
from worktree.cli import app
from worktree.cli.task.command import task_run_command
from worktree.core.db import RunStatus, TasksDb
from worktree.core.runtime import FailurePromptDecision, RunOutcome
from worktree.core.step import StepDefinition, StepResult

runner = CliRunner()


def test_task_run_command_steps_execution(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "build-task",
        description="Build and test task",
        summary="Build and test",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo step1"},
            {"id": "step-2", "run": "echo step2"},
        ],
    )

    res = task_run_command("build-task", cwd=fs.base_path, session_id="task_build_1")
    assert res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "completed"

    rec = TasksDb(fs.base_path).get("task_build_1")
    assert rec is not None
    assert rec.status.value == "completed"


def test_task_run_cli_options(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "lint-task",
        description="Lint task",
        summary="Lint task",
        use_sandbox=False,
        steps=[{"id": "check-lints", "run": "echo lint ok"}],
    )

    result = runner.invoke(
        app,
        ["task", "run", "lint-task", "--no-sandbox", "--agent", "claude-3-5-sonnet"],
    )
    assert result.exit_code == 0
    assert "Task Run Completed:" in result.output
    assert "Sandbox: In-place (workspace)" in result.output


def test_task_run_step_failure_aborts(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "failing-task",
        description="Failing task",
        summary="Failing task",
        use_sandbox=False,
        steps=[
            {"id": "pass-step", "run": "echo ok"},
            {"id": "fail-step", "run": "exit 1", "on_failure": "abort"},
            {"id": "unreachable-step", "run": "echo should not run"},
        ],
    )

    res = task_run_command("failing-task", cwd=fs.base_path, session_id="task_fail_1")
    assert not res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "failed"

    rec = TasksDb(fs.base_path).get("task_fail_1")
    assert rec is not None
    assert rec.status.value == "failed"
    assert rec.error_message is not None
    assert "fail-step" in rec.error_message


def test_task_run_prompt_user_persists_paused_checkpoint(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "pause-task",
        use_sandbox=False,
        steps=[{"id": "fail-step", "run": "exit 1", "on_failure": "prompt_user"}],
    )

    class _InterruptPrompter:
        def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
            raise KeyboardInterrupt

        @property
        def is_interactive(self) -> bool:
            return True

    monkeypatch.setattr(
        "worktree.cli.task.command.CliFailurePrompter",
        lambda *args, **kwargs: _InterruptPrompter(),
    )
    monkeypatch.setattr(
        "worktree.core.runtime.engine.execute_step",
        lambda step, sandbox_path, context=None: StepResult(
            step_id=step.id if isinstance(step, StepDefinition) else "fail-step",
            status="failed",
            exit_code=1,
            stdout="",
            stderr="nope",
            duration_seconds=0.01,
            error_message="boom",
        ),
    )

    res = task_run_command("pause-task", cwd=fs.base_path, session_id="task_pause_1")
    assert res.ok
    rec = TasksDb(fs.base_path).get("task_pause_1")
    assert rec is not None
    assert rec.status is RunStatus.PAUSED
    assert rec.completed_at is None
    assert rec.checkpoint_json is not None
    assert "fail-step" in rec.checkpoint_json


def test_task_run_keep_retains_sandbox(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "keep-task",
        use_sandbox=True,
        steps=[{"id": "ok", "run": "echo ok"}],
    )

    kept_path = fs.base_path / ".worktree" / "sandboxes" / "kept"
    kept_path.mkdir(parents=True, exist_ok=True)

    def _fake_run_task(
        definition,
        cwd,
        *,
        use_sandbox=True,
        keep=False,
        agent=None,
        observer=None,
        inputs=None,
        **kwargs,
    ):
        if observer is not None:
            observer.on_sandbox_ready(kept_path, True)
            observer.on_sandbox_cleanup(True, kept_path)
        return RunOutcome(
            status=RunStatus.COMPLETED,
            step_results=[],
            error_message=None,
            sandbox_kept=True,
            sandbox_path=kept_path,
        )

    monkeypatch.setattr("worktree.cli.task.command.run_task", _fake_run_task)

    result = runner.invoke(app, ["task", "run", "keep-task", "--keep"])
    assert result.exit_code == 0
    assert "Sandbox: Retained" in result.output


def test_task_run_missing_task_skips_db_insert(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    insert = MagicMock()
    monkeypatch.setattr(TasksDb, "insert", insert)

    res = task_run_command("missing-task", cwd=fs.base_path, session_id="task_missing")
    assert not res.ok
    assert res.run_record is None
    insert.assert_not_called()
    assert TasksDb(fs.base_path).get("task_missing") is None


def test_task_run_cancelled_status(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "cancel-task",
        use_sandbox=False,
        steps=[{"id": "ok", "run": "echo ok"}],
    )

    def _fake_run_task(
        definition,
        cwd,
        *,
        use_sandbox=True,
        keep=False,
        agent=None,
        observer=None,
        inputs=None,
        **kwargs,
    ):
        return RunOutcome(
            status=RunStatus.CANCELLED,
            step_results=[],
            error_message="Execution cancelled by user.",
            sandbox_kept=False,
            sandbox_path=cwd,
        )

    monkeypatch.setattr("worktree.cli.task.command.run_task", _fake_run_task)

    res = task_run_command("cancel-task", cwd=fs.base_path, session_id="task_canc1")
    assert not res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "cancelled"

    rec = TasksDb(fs.base_path).get("task_canc1")
    assert rec is not None
    assert rec.status.value == "cancelled"
    assert "cancelled" in (rec.error_message or "").lower()


def test_task_run_uses_step_with_override(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blueprint uses: references a catalog step and applies a field override."""
    monkeypatch.chdir(fs.base_path)
    fs.create_step_file(step_id="greet", command="echo from-catalog-step")
    fs.create_task_file(
        "uses-task",
        description="Task that references a catalog step",
        summary="uses step",
        use_sandbox=False,
        steps=[
            {
                "id": "greet-step",
                "uses": "greet",
                "name": "overridden-greet",
            }
        ],
    )

    res = task_run_command("uses-task", cwd=fs.base_path, session_id="task_uses_1")
    assert res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "completed"

    rec = TasksDb(fs.base_path).get("task_uses_1")
    assert rec is not None
    assert rec.status.value == "completed"


def test_task_run_honors_step_assert_block(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Task YAML assert is loaded and gates step success through execute_step."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "assert-task",
        description="Task with assert",
        summary="assert task",
        use_sandbox=False,
        steps=[
            {
                "id": "make-artifact",
                "run": "echo ok",
                "assert": {"file_exists": "missing.bin"},
            }
        ],
    )

    res = task_run_command("assert-task", cwd=fs.base_path, session_id="task_assert_1")
    assert not res.ok
    assert res.run_record is not None
    assert res.run_record.status.value == "failed"
    assert res.run_record.error_message is not None
    assert "failed assertion checks" in res.run_record.error_message
    assert "missing.bin" in res.run_record.error_message


def test_task_run_invalid_assert_aborts_before_steps(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsafe assert paths fail task load; no run record and no step execution."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "bad-assert-task",
        description="Invalid assert paths",
        summary="bad assert",
        use_sandbox=False,
        steps=[
            {
                "id": "unsafe-step",
                "run": "echo should-not-run",
                "assert": {"file_exists": "../etc/passwd"},
            }
        ],
    )

    run_task = MagicMock()
    monkeypatch.setattr("worktree.cli.task.command.run_task", run_task)

    res = task_run_command("bad-assert-task", cwd=fs.base_path, session_id="task_bad_assert")
    assert not res.ok
    assert res.run_record is None
    run_task.assert_not_called()
    assert any("assert" in err.lower() or "validation" in err.lower() for err in res.errors)
    assert TasksDb(fs.base_path).get("task_bad_assert") is None


def test_task_run_missing_required_input_skips_execution(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "commit",
        use_sandbox=False,
        inputs={
            "message": {
                "type": "string",
                "required": True,
                "aliases": ["-m", "--message"],
            }
        },
        steps=[
            {
                "id": "git-commit",
                "type": "command",
                "command": "echo '${{ inputs.message }}'",
            }
        ],
    )

    run_task = MagicMock()
    monkeypatch.setattr("worktree.cli.task.command.run_task", run_task)

    res = task_run_command("commit", cwd=fs.base_path, session_id="task_missing_input")
    assert not res.ok
    assert res.run_record is None
    run_task.assert_not_called()
    assert any("Missing required input 'message'" in err for err in res.errors)
    assert TasksDb(fs.base_path).get("task_missing_input") is None


def test_task_run_cli_alias_interpolates_input(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "commit",
        use_sandbox=False,
        inputs={
            "message": {
                "type": "string",
                "required": True,
                "aliases": ["-m", "--message"],
            }
        },
        steps=[
            {
                "id": "git-commit",
                "type": "command",
                "command": "echo '${{ inputs.message }}'",
            }
        ],
    )

    result = runner.invoke(app, ["task", "run", "commit", "--no-sandbox", "-m", "ship it"])
    assert result.exit_code == 0
    assert "Task Run Completed:" in result.output


def test_task_run_cli_input_override(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "echo-msg",
        use_sandbox=False,
        inputs={
            "message": {
                "type": "string",
                "required": True,
            }
        },
        steps=[
            {
                "id": "print",
                "type": "command",
                "command": "echo '${{ inputs.message }}'",
            }
        ],
    )

    result = runner.invoke(
        app,
        ["task", "run", "echo-msg", "--no-sandbox", "-i", "message=from-i"],
    )
    assert result.exit_code == 0
    assert "Task Run Completed:" in result.output


def test_task_run_non_interactive_flag_forwarded(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "ni-task",
        use_sandbox=False,
        steps=[{"id": "ok", "run": "echo ok"}],
    )
    captured = {}

    def _fake_run_task(definition, cwd, **kwargs):
        captured.update(kwargs)
        return RunOutcome(
            status=RunStatus.COMPLETED,
            step_results=[],
            error_message=None,
            sandbox_kept=False,
            sandbox_path=cwd,
        )

    monkeypatch.setattr("worktree.cli.task.command.run_task", _fake_run_task)
    # Force non-interactive path even if TTY
    res = task_run_command("ni-task", cwd=fs.base_path, non_interactive=True, session_id="task_ni1")
    assert res.ok
    assert captured.get("non_interactive") is True
    assert captured.get("failure_prompter") is None
