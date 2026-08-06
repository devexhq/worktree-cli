from pathlib import Path

from getworktree.core.step import (
    FailureAction,
    StepDefinition,
    StepResult,
    StepType,
    execute_step,
)


def test_step_result_ok_property():
    res_completed = StepResult(
        step_id="s1",
        status="completed",
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.1,
    )
    assert res_completed.ok is True

    res_ignored = StepResult(
        step_id="s2",
        status="ignored",
        exit_code=0,
        stdout="",
        stderr="warning",
        duration_seconds=0.2,
    )
    assert res_ignored.ok is True

    res_failed = StepResult(
        step_id="s3",
        status="failed",
        exit_code=1,
        stdout="",
        stderr="error",
        duration_seconds=0.3,
    )
    assert res_failed.ok is False


def test_execute_command_step_success(tmp_path: Path):
    step = StepDefinition(
        id="cmd_success",
        name="cmd-success",
        type=StepType.COMMAND,
        description="Run echo",
        command="echo 'hello world'",
    )

    res = execute_step(step, sandbox_path=tmp_path)
    assert res.ok is True
    assert res.status == "completed"
    assert res.exit_code == 0
    assert "hello world" in res.stdout
    assert res.attempts == 1


def test_execute_command_step_failure_abort(tmp_path: Path):
    step = StepDefinition(
        id="cmd_fail",
        name="cmd-fail",
        type=StepType.COMMAND,
        description="Run failing command",
        command="exit 42",
        failure_action=FailureAction.ABORT,
    )

    res = execute_step(step, sandbox_path=tmp_path)
    assert res.ok is False
    assert res.status == "failed"
    assert res.exit_code == 42
    assert res.attempts == 1
    assert "exit code 42" in (res.error_message or "")


def test_execute_command_step_failure_ignore(tmp_path: Path):
    step = StepDefinition(
        id="cmd_ignore",
        name="cmd-ignore",
        type=StepType.COMMAND,
        description="Ignore failure",
        command="exit 1",
        failure_action=FailureAction.IGNORE,
    )

    res = execute_step(step, sandbox_path=tmp_path)
    assert res.ok is True
    assert res.status == "ignored"
    assert res.exit_code == 0
    assert res.attempts == 1


def test_execute_command_step_retry(tmp_path: Path):
    counter_file = tmp_path / "count.txt"
    # Write shell command that increments counter in file and fails first 2 tries
    cmd = (
        f"python3 -c \"import pathlib; p = pathlib.Path('{counter_file}'); "
        "val = int(p.read_text()) if p.exists() else 0; p.write_text(str(val + 1)); "
        'import sys; sys.exit(0 if val >= 2 else 1)"'
    )

    step = StepDefinition(
        id="cmd_retry",
        name="cmd-retry",
        type=StepType.COMMAND,
        description="Retry 3 times",
        command=cmd,
        failure_action=FailureAction.RETRY,
    )

    res = execute_step(step, sandbox_path=tmp_path)
    assert res.ok is True
    assert res.status == "completed"
    assert res.exit_code == 0
    assert res.attempts == 3
    assert counter_file.read_text() == "3"


def test_execute_command_step_timeout(tmp_path: Path):
    step = StepDefinition(
        id="cmd_timeout",
        name="cmd-timeout",
        type=StepType.COMMAND,
        description="Sleep long",
        command="sleep 5",
        timeout_seconds=1,
    )

    res = execute_step(step, sandbox_path=tmp_path)
    assert res.ok is False
    assert res.status == "failed"
    assert "timed out" in (res.error_message or "").lower()


def test_execute_script_step(tmp_path: Path):
    script_file = tmp_path / "test_script.py"
    script_file.write_text("print('script output')", encoding="utf-8")

    step = StepDefinition(
        id="script_step",
        name="script-step",
        type=StepType.SCRIPT,
        description="Run script",
        script_path="test_script.py",
    )

    res = execute_step(step, sandbox_path=tmp_path)
    assert res.ok is True
    assert res.status == "completed"
    assert "script output" in res.stdout


def test_execute_script_step_missing_file(tmp_path: Path):
    step = StepDefinition(
        id="script_missing",
        name="script-missing",
        type=StepType.SCRIPT,
        description="Run missing script",
        script_path="nonexistent.sh",
    )

    res = execute_step(step, sandbox_path=tmp_path)
    assert res.ok is False
    assert res.status == "failed"
    assert "not found" in (res.error_message or "").lower()


def test_execute_agent_step_custom_handler(tmp_path: Path):
    def custom_handler(step_def, sb_path, ctx):
        return "completed", 0, "agent result", "", None

    step = StepDefinition(
        id="agent_step",
        name="agent-step",
        type=StepType.AGENT,
        description="Run agent prompt",
        prompt="Fix bugs",
        tools=["edit_file"],
    )

    res = execute_step(
        step, sandbox_path=tmp_path, context={"agent_handler": custom_handler}
    )
    assert res.ok is True
    assert res.status == "completed"
    assert res.stdout == "agent result"


def test_execute_step_invalid_sandbox_path(tmp_path: Path):
    nonexistent = tmp_path / "sandbox_missing"
    step = StepDefinition(
        id="step_sb",
        name="step-sb",
        type=StepType.COMMAND,
        description="Test",
        command="echo 1",
    )

    res = execute_step(step, sandbox_path=nonexistent)
    assert res.ok is False
    assert res.status == "failed"
    assert "does not exist" in (res.error_message or "").lower()
