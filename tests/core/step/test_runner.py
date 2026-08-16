import pytest

from getworktree.core.step import StepAssert, StepDefinition, StepResult, StepType, execute_step
from getworktree.core.step.runner import StepDispatchOutcome
from tests.helpers import FileSystem


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


def test_execute_command_step_success(fs: FileSystem):
    step = StepDefinition(
        id="cmd_success",
        type=StepType.COMMAND,
        command="echo 'hello world'",
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "completed"
    assert res.exit_code == 0
    assert "hello world" in res.stdout
    assert res.attempts == 1


def test_execute_command_step_failure_abort(fs: FileSystem):
    step = StepDefinition(
        id="cmd_fail",
        type=StepType.COMMAND,
        command="exit 42",
        on_failure="abort",
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is False
    assert res.status == "failed"
    assert res.exit_code == 42
    assert res.attempts == 1
    assert "exit code 42" in (res.error_message or "")


def test_execute_command_step_failure_continue_is_ignored(fs: FileSystem):
    step = StepDefinition(
        id="cmd_ignore",
        type=StepType.COMMAND,
        command="exit 1",
        on_failure="continue",
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "ignored"
    assert res.exit_code == 0
    assert res.attempts == 1


def test_execute_command_step_retry_exhausted_aborts_by_default(fs: FileSystem):
    step = StepDefinition(
        id="cmd_retry_fail",
        type=StepType.COMMAND,
        command="exit 1",
        on_failure={"action": "retry", "max_retries": 2},
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is False
    assert res.status == "failed"
    assert res.attempts == 2


def test_execute_command_step_retry_exhausted_continue_is_ignored(fs: FileSystem):
    step = StepDefinition(
        id="cmd_retry_continue",
        type=StepType.COMMAND,
        command="exit 1",
        on_failure={"action": "retry", "max_retries": 2, "on_max_retries": "continue"},
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "ignored"
    assert res.attempts == 2


def test_execute_command_step_retry_sleeps_backoff_between_attempts(fs: FileSystem, monkeypatch: pytest.MonkeyPatch):
    sleep_calls: list[float] = []
    monkeypatch.setattr("getworktree.core.step.runner.time.sleep", lambda secs: sleep_calls.append(secs))

    step = StepDefinition(
        id="cmd_backoff",
        type=StepType.COMMAND,
        command="exit 1",
        on_failure={"action": "retry", "max_retries": 3, "backoff_ms": 250},
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.attempts == 3
    assert sleep_calls == [0.25, 0.25]


def test_execute_command_step_retry(fs: FileSystem):
    counter_file = fs.base_path / "count.txt"
    # Write shell command that increments counter in file and fails first 2 tries
    cmd = (
        f"python3 -c \"import pathlib; p = pathlib.Path('{counter_file}'); "
        "val = int(p.read_text()) if p.exists() else 0; p.write_text(str(val + 1)); "
        'import sys; sys.exit(0 if val >= 2 else 1)"'
    )

    step = StepDefinition(
        id="cmd_retry",
        type=StepType.COMMAND,
        command=cmd,
        on_failure="retry",
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "completed"
    assert res.exit_code == 0
    assert res.attempts == 3
    assert counter_file.read_text() == "3"


def test_execute_command_step_timeout(fs: FileSystem):
    step = StepDefinition(
        id="cmd_timeout",
        type=StepType.COMMAND,
        command="sleep 5",
        timeout_seconds=1,
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is False
    assert res.status == "failed"
    assert "timed out" in (res.error_message or "").lower()


def test_execute_script_step(fs: FileSystem):
    fs.write_file("test_script.py", "print('script output')")

    step = StepDefinition(
        id="script_step",
        type=StepType.SCRIPT,
        script_path="test_script.py",
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "completed"
    assert "script output" in res.stdout


def test_execute_script_step_missing_file(fs: FileSystem):
    step = StepDefinition(
        id="script_missing",
        type=StepType.SCRIPT,
        script_path="nonexistent.sh",
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is False
    assert res.status == "failed"
    assert "not found" in (res.error_message or "").lower()


def test_execute_agent_step_custom_handler(fs: FileSystem):
    def custom_handler(step_def, sb_path, ctx):
        return StepDispatchOutcome(
            status="completed",
            exit_code=0,
            stdout="agent result",
            stderr="",
        )

    step = StepDefinition(
        id="agent_step",
        type=StepType.AGENT,
        prompt="Fix bugs",
        tools=["edit_file"],
    )

    res = execute_step(step, sandbox_path=fs.base_path, context={"agent_handler": custom_handler})
    assert res.ok is True
    assert res.status == "completed"
    assert res.stdout == "agent result"


def test_execute_agent_step_defaults_to_local_provider(fs: FileSystem):
    step = StepDefinition(id="agent_step", type=StepType.AGENT, prompt="Fix bugs")

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "completed"


def test_execute_agent_step_uses_context_provider_override(fs: FileSystem):
    step = StepDefinition(id="agent_step", type=StepType.AGENT, prompt="Fix bugs")

    res = execute_step(step, sandbox_path=fs.base_path, context={"agent": "ollama"})
    assert res.ok is True


def test_execute_step_invalid_sandbox_path(fs: FileSystem):
    nonexistent = fs.base_path / "sandbox_missing"
    step = StepDefinition(
        id="step_sb",
        type=StepType.COMMAND,
        command="echo 1",
    )

    res = execute_step(step, sandbox_path=nonexistent)
    assert res.ok is False
    assert res.status == "failed"
    assert "does not exist" in (res.error_message or "").lower()


def test_execute_step_resolves_run_shorthand(fs: FileSystem):
    step = StepDefinition(id="run-step", run="echo from-run")

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert "from-run" in res.stdout


def test_execute_step_resolves_uses_reference(fs: FileSystem):
    fs.create_step_file(step_id="greet", command="echo from-uses")

    step = StepDefinition(id="uses-step", uses="greet")

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert "from-uses" in res.stdout


def test_execute_step_assertion_failure_keeps_exit_code(fs: FileSystem):
    """Exit 0 with a missing asserted file is still a failed step; exit_code stays 0."""
    step = StepDefinition(
        id="assert-missing-file",
        name="build-artifact",
        type=StepType.COMMAND,
        command="echo built",
        assert_=StepAssert(file_exists="dist/app.bin"),
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is False
    assert res.status == "failed"
    assert res.exit_code == 0
    assert res.attempts == 1
    assert res.error_message is not None
    assert "Step 'build-artifact' failed assertion checks:" in res.error_message
    assert "[FAIL]" in res.error_message
    assert "dist/app.bin" in res.error_message


def test_execute_step_assertion_failure_retries_until_pass(fs: FileSystem):
    """failure_action=retry re-runs until the asserted file appears."""
    marker = fs.base_path / "artifact.bin"
    cmd = (
        f"python3 -c \"from pathlib import Path; p = Path('{marker}'); "
        "n = int(p.with_suffix('.count').read_text()) if p.with_suffix('.count').exists() else 0; "
        "p.with_suffix('.count').write_text(str(n + 1)); "
        "p.write_text('ok') if n >= 2 else None\""
    )
    step = StepDefinition(
        id="assert-retry",
        type=StepType.COMMAND,
        command=cmd,
        assert_=StepAssert(file_exists="artifact.bin"),
        on_failure={"action": "retry", "max_retries": 3, "backoff_ms": 0},
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "completed"
    assert res.exit_code == 0
    assert res.attempts == 3
    assert marker.exists()


def test_execute_step_assertion_failure_continue_is_ignored(fs: FileSystem):
    """on_failure=continue marks assertion failures ignored while keeping the diagnostic."""
    step = StepDefinition(
        id="assert-continue",
        type=StepType.COMMAND,
        command="echo ok",
        assert_=StepAssert(file_exists="missing.bin"),
        on_failure="continue",
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "ignored"
    assert res.exit_code == 0
    assert res.error_message is not None
    assert "failed assertion checks" in res.error_message


def test_execute_step_assertion_passes_when_file_exists(fs: FileSystem):
    fs.write_file("dist/app.bin", "payload")
    step = StepDefinition(
        id="assert-pass",
        type=StepType.COMMAND,
        command="echo ok",
        assert_=StepAssert(file_exists="dist/app.bin"),
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is True
    assert res.status == "completed"
    assert res.exit_code == 0
    assert res.error_message is None


def test_execute_agent_step_assertions_apply_to_placeholder_stdout(fs: FileSystem):
    step = StepDefinition(
        id="agent-assert",
        type=StepType.AGENT,
        prompt="do work",
        assert_=StepAssert(output_contains="never-present-token"),
    )

    res = execute_step(step, sandbox_path=fs.base_path)
    assert res.ok is False
    assert res.status == "failed"
    assert res.exit_code == 0
    assert res.error_message is not None
    assert "failed assertion checks" in res.error_message


def test_execute_command_step_interpolates_inputs(fs: FileSystem):
    step = StepDefinition(
        id="cmd_inputs",
        type=StepType.COMMAND,
        command="echo '${{ inputs.message }}'",
    )

    res = execute_step(
        step,
        sandbox_path=fs.base_path,
        context={"inputs": {"message": "interpolated-value"}},
    )
    assert res.ok is True
    assert "interpolated-value" in res.stdout
