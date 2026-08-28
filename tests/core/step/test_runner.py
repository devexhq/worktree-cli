import pytest

from tests.helpers import FileSystem
from worktree.core.step import StepAssert, StepDefinition, StepResult, StepType, execute_step


class StepResultModelTests:
    """Unit tests for StepResult properties and status flags."""

    def test_step_result_ok_property(self) -> None:
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


class StepRunnerExecutionTests:
    """Unit tests for single-step dispatch across command, script, and agent steps."""

    def test_execute_command_step_success(self, fs: FileSystem) -> None:
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

    def test_execute_command_step_failure_abort(self, fs: FileSystem) -> None:
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

    def test_execute_command_step_failure_continue_is_ignored(self, fs: FileSystem) -> None:
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

    def test_execute_command_step_timeout(self, fs: FileSystem) -> None:
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

    def test_execute_script_step(self, fs: FileSystem) -> None:
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

    def test_execute_script_step_missing_file(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="script_missing",
            type=StepType.SCRIPT,
            script_path="nonexistent.sh",
        )

        res = execute_step(step, sandbox_path=fs.base_path)
        assert res.ok is False
        assert res.status == "failed"
        assert "not found" in (res.error_message or "").lower()

    def test_execute_agent_step_defaults_to_local_provider(self, fs: FileSystem) -> None:
        step = StepDefinition(id="agent_step", type=StepType.AGENT, prompt="Fix bugs")

        res = execute_step(step, sandbox_path=fs.base_path)
        assert res.ok is True
        assert res.status == "completed"

    def test_execute_agent_step_uses_context_provider_override(self, fs: FileSystem) -> None:
        step = StepDefinition(id="agent_step", type=StepType.AGENT, prompt="Fix bugs")

        res = execute_step(step, sandbox_path=fs.base_path, context={"agent": "ollama"})
        assert res.ok is True

    def test_execute_step_invalid_sandbox_path(self, fs: FileSystem) -> None:
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

    def test_execute_step_resolves_run_shorthand(self, fs: FileSystem) -> None:
        step = StepDefinition(id="run-step", run="echo from-run")

        res = execute_step(step, sandbox_path=fs.base_path)
        assert res.ok is True
        assert "from-run" in res.stdout

    def test_execute_step_resolves_uses_reference(self, fs: FileSystem) -> None:
        fs.create_step_file(step_id="greet", command="echo from-uses")

        step = StepDefinition(id="uses-step", uses="greet")

        res = execute_step(step, sandbox_path=fs.base_path)
        assert res.ok is True
        assert "from-uses" in res.stdout

    def test_execute_command_step_interpolates_inputs(self, fs: FileSystem) -> None:
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


class StepRunnerRetryTests:
    """Unit tests for retry policies, max retry limits, and backoff sleeps in step runner."""

    def test_execute_command_step_retry_exhausted_aborts_by_default(self, fs: FileSystem) -> None:
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

    def test_execute_command_step_retry_exhausted_continue_is_ignored(self, fs: FileSystem) -> None:
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

    def test_execute_command_step_retry_sleeps_backoff_between_attempts(
        self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        original_sleep = time.sleep
        sleep_calls: list[float] = []

        def mock_sleep(secs: float) -> None:
            if secs >= 0.1:
                sleep_calls.append(secs)
            else:
                original_sleep(secs)

        monkeypatch.setattr("worktree.core.step.runner.time.sleep", mock_sleep)

        step = StepDefinition(
            id="cmd_backoff",
            type=StepType.COMMAND,
            command="exit 1",
            on_failure={"action": "retry", "max_retries": 3, "backoff_ms": 250},
        )

        res = execute_step(step, sandbox_path=fs.base_path)
        assert res.attempts == 3
        assert sleep_calls == [0.25, 0.25]

    def test_execute_command_step_retry(self, fs: FileSystem) -> None:
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


class StepRunnerAssertionTests:
    """Unit tests for step-level assertions on file existence, outputs, and exit codes."""

    def test_execute_step_assertion_failure_keeps_exit_code(self, fs: FileSystem) -> None:
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

    def test_execute_step_assertion_failure_retries_until_pass(self, fs: FileSystem) -> None:
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

    def test_execute_step_assertion_failure_continue_is_ignored(self, fs: FileSystem) -> None:
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

    def test_execute_step_assertion_passes_when_file_exists(self, fs: FileSystem) -> None:
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

    def test_execute_agent_step_assertions_apply_to_placeholder_stdout(self, fs: FileSystem) -> None:
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


class StepRunnerStreamingOutputTests:
    """Unit tests for real-time subprocess stdout/stderr line streaming and timeout retention."""

    def test_execute_command_step_streams_stdout(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="stream-stdout",
            type=StepType.COMMAND,
            command="python3 -c \"print('line 1'); print('line 2'); print('line 3')\"",
        )
        streamed: list[tuple[str, str]] = []

        res = execute_step(
            step,
            sandbox_path=fs.base_path,
            on_output=lambda stream, line: streamed.append((stream, line)),
        )

        assert res.ok is True
        assert res.status == "completed"
        assert res.exit_code == 0
        assert res.stdout == "line 1\nline 2\nline 3\n"
        assert streamed == [
            ("stdout", "line 1\n"),
            ("stdout", "line 2\n"),
            ("stdout", "line 3\n"),
        ]

    def test_execute_command_step_streams_stderr(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="stream-stderr",
            type=StepType.COMMAND,
            command="python3 -c \"import sys; sys.stderr.write('err 1\\nerr 2\\n'); sys.stderr.flush()\"",
        )
        streamed: list[tuple[str, str]] = []

        res = execute_step(
            step,
            sandbox_path=fs.base_path,
            on_output=lambda stream, line: streamed.append((stream, line)),
        )

        assert res.ok is True
        assert res.exit_code == 0
        assert res.stderr == "err 1\nerr 2\n"
        assert streamed == [
            ("stderr", "err 1\n"),
            ("stderr", "err 2\n"),
        ]

    def test_execute_command_step_streams_interleaved_stdout_and_stderr(self, fs: FileSystem) -> None:
        cmd = (
            'python3 -c "'
            "import sys; "
            "print('out 1', flush=True); "
            "sys.stderr.write('err 1\\n'); sys.stderr.flush(); "
            "print('out 2', flush=True); "
            "sys.stderr.write('err 2\\n'); sys.stderr.flush()"
            '"'
        )
        step = StepDefinition(id="interleaved", type=StepType.COMMAND, command=cmd)
        streamed: list[tuple[str, str]] = []

        res = execute_step(
            step,
            sandbox_path=fs.base_path,
            on_output=lambda stream, line: streamed.append((stream, line)),
        )

        assert res.ok is True
        assert "out 1\nout 2\n" == res.stdout
        assert "err 1\nerr 2\n" == res.stderr
        assert ("stdout", "out 1\n") in streamed
        assert ("stderr", "err 1\n") in streamed
        assert ("stdout", "out 2\n") in streamed
        assert ("stderr", "err 2\n") in streamed

    def test_execute_command_step_large_output_no_deadlock(self, fs: FileSystem) -> None:
        # Emit large chunks on both stdout and stderr (over 100KB each) to ensure no pipe deadlocks
        cmd = (
            'python3 -c "import sys\n'
            "for i in range(2000):\n"
            "    print('stdout line ' + str(i))\n"
            "    sys.stderr.write('stderr line ' + str(i) + '\\n')\n"
            '"'
        )
        step = StepDefinition(id="large-burst", type=StepType.COMMAND, command=cmd)
        lines_received: list[str] = []

        res = execute_step(
            step,
            sandbox_path=fs.base_path,
            on_output=lambda stream, line: lines_received.append(line),
        )

        assert res.ok is True
        assert len(lines_received) == 4000
        assert res.stdout.count("\n") == 2000
        assert res.stderr.count("\n") == 2000

    def test_execute_command_step_timeout_retains_partial_output_and_exit_124(self, fs: FileSystem) -> None:
        cmd = (
            'python3 -c "'
            "import time, sys; "
            "print('initial stdout line', flush=True); "
            "sys.stderr.write('initial stderr line\\n'); sys.stderr.flush(); "
            "time.sleep(5)"
            '"'
        )
        step = StepDefinition(id="timeout-partial", type=StepType.COMMAND, command=cmd, timeout_seconds=1)
        streamed: list[tuple[str, str]] = []

        res = execute_step(
            step,
            sandbox_path=fs.base_path,
            on_output=lambda stream, line: streamed.append((stream, line)),
        )

        assert res.ok is False
        assert res.status == "failed"
        assert res.exit_code == 124
        assert "timed out" in (res.error_message or "").lower()
        assert "initial stdout line\n" == res.stdout
        assert "initial stderr line\n" == res.stderr
        assert ("stdout", "initial stdout line\n") in streamed
        assert ("stderr", "initial stderr line\n") in streamed

    def test_execute_command_step_timeout_terminates_process_tree(self, fs: FileSystem) -> None:
        marker = fs.base_path / "tree_alive.txt"
        cmd = f"python3 -c \"import time, pathlib; pathlib.Path('{marker}').write_text('running'); time.sleep(10)\""
        step = StepDefinition(id="tree-timeout", type=StepType.COMMAND, command=cmd, timeout_seconds=1)

        res = execute_step(step, sandbox_path=fs.base_path)
        assert res.ok is False
        assert res.exit_code == 124
        assert marker.read_text() == "running"

    def test_execute_script_step_streams_output(self, fs: FileSystem) -> None:
        fs.write_file(
            "stream_script.py",
            "import sys\nprint('script stdout line')\nsys.stderr.write('script stderr line\\n')\n",
        )
        step = StepDefinition(
            id="script-stream",
            type=StepType.SCRIPT,
            script_path="stream_script.py",
        )
        streamed: list[tuple[str, str]] = []

        res = execute_step(
            step,
            sandbox_path=fs.base_path,
            on_output=lambda stream, line: streamed.append((stream, line)),
        )

        assert res.ok is True
        assert res.stdout == "script stdout line\n"
        assert res.stderr == "script stderr line\n"
        assert ("stdout", "script stdout line\n") in streamed
        assert ("stderr", "script stderr line\n") in streamed

    def test_execute_command_step_handles_on_output_callback_error(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="cmd-callback-err",
            type=StepType.COMMAND,
            command="echo hello",
        )

        def failing_callback(stream: str, line: str) -> None:
            raise RuntimeError("callback crashed")

        res = execute_step(step, sandbox_path=fs.base_path, on_output=failing_callback)
        assert res.ok is False
        assert res.status == "failed"
        assert "callback crashed" in (res.error_message or "")
        assert "Output callback error" in (res.error_message or "")

    def test_execute_agent_step_handles_on_output_callback_error(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="agent-callback-err",
            type=StepType.AGENT,
            prompt="Do task",
        )

        def failing_callback(stream: str, line: str) -> None:
            raise ValueError("agent callback fail")

        res = execute_step(step, sandbox_path=fs.base_path, on_output=failing_callback)
        assert res.ok is False
        assert res.status == "failed"
        assert "agent callback fail" in (res.error_message or "")
        assert "Agent output callback error" in (res.error_message or "")
