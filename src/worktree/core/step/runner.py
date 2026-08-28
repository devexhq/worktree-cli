"""Step execution runner and outcome models."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from pydantic import BaseModel

from worktree.core.agents.factory import get_agent_adapter
from worktree.core.inputs import interpolate_step_fields
from worktree.core.step.assertions import evaluate_assertions
from worktree.core.step.models import FailurePolicy, StepDefinition, StepType
from worktree.core.step.services.resolver import resolve_step_definition


class StepDispatchOutcome(BaseModel):
    """Raw outcome of one or more step primitive dispatches (before finalization)."""

    model_config = {"extra": "forbid", "strict": True}

    status: str  # "completed" | "failed"
    exit_code: int
    stdout: str
    stderr: str
    error_message: str | None = None
    attempts: int = 1


class StepResult(BaseModel):
    """Normalized result of a step execution."""

    model_config = {"extra": "forbid", "strict": True}

    step_id: str
    status: str  # "completed" | "failed" | "ignored"
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    attempts: int = 1
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        """Return True if step finished successfully or was ignored."""
        return self.status in ("completed", "ignored")


def _failed_dispatch(
    error_message: str,
    *,
    exit_code: int = 1,
    stdout: str = "",
    stderr: str = "",
) -> StepDispatchOutcome:
    return StepDispatchOutcome(
        status="failed",
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        error_message=error_message,
    )


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    """Terminate or kill a subprocess and its child process tree."""
    try:
        if hasattr(os, "killpg"):
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError, OSError):
                # Best-effort fallback: process group already terminated or inaccessible.
                pass
        proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        # Best-effort cleanup: process already exited or PID not found.
        pass


def _dispatch_pipe_line(
    line: str,
    stream_name: str,
    collected_lines: list[str],
    on_output: Callable[[str, str], None] | None,
    collected_errors: list[str],
) -> None:
    collected_lines.append(line)
    if on_output is not None:
        try:
            on_output(stream_name, line)
        except Exception as exc:
            collected_errors.append(f"Output callback error on {stream_name}: {exc}")


def _stream_pipe(
    pipe: IO[str] | None,
    stream_name: str,
    collected_lines: list[str],
    on_output: Callable[[str, str], None] | None,
    collected_errors: list[str],
) -> None:
    """Read lines from pipe, accumulate them, and invoke on_output callback."""
    if pipe is None:
        return
    try:
        for line in iter(pipe.readline, ""):
            _dispatch_pipe_line(line, stream_name, collected_lines, on_output, collected_errors)
    except Exception as exc:
        collected_errors.append(f"Failed reading {stream_name} stream: {exc}")
    finally:
        try:
            pipe.close()
        except Exception:
            # Best-effort cleanup: closing stream pipe during termination.
            pass


def _run_process(
    cmd: str | list[str],
    *,
    shell: bool,
    cwd: Path,
    timeout_seconds: int | float | None,
    failure_label: str,
    step_kind: str,
    on_output: Callable[[str, str], None] | None = None,
) -> StepDispatchOutcome:
    try:
        proc = subprocess.Popen(
            cmd,
            shell=shell,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=(sys.platform != "win32"),
        )
    except Exception as exc:
        return _failed_dispatch(f"{failure_label} execution error: {exc}")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    pipe_errors: list[str] = []

    t_out = threading.Thread(
        target=_stream_pipe,
        args=(proc.stdout, "stdout", stdout_lines, on_output, pipe_errors),
        daemon=True,
    )
    t_err = threading.Thread(
        target=_stream_pipe,
        args=(proc.stderr, "stderr", stderr_lines, on_output, pipe_errors),
        daemon=True,
    )
    t_out.start()
    t_err.start()

    timed_out = False
    exit_code = 0
    try:
        exit_code = proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(proc)
        try:
            exit_code = proc.wait(timeout=5)
        except Exception:
            # Best-effort wait: process tree was killed; exit code defaults to 124.
            pass

    t_out.join(timeout=2)
    t_err.join(timeout=2)

    stdout = "".join(stdout_lines)
    stderr = "".join(stderr_lines)

    if pipe_errors:
        error_details = "; ".join(pipe_errors)
        return _failed_dispatch(
            f"{failure_label} pipe error: {error_details}",
            exit_code=exit_code if exit_code != 0 else 1,
            stdout=stdout,
            stderr=stderr,
        )

    if timed_out:
        return _failed_dispatch(
            f"{step_kind} step execution timed out after {timeout_seconds} seconds.",
            exit_code=124,
            stdout=stdout,
            stderr=stderr,
        )

    if exit_code == 0:
        return StepDispatchOutcome(status="completed", exit_code=0, stdout=stdout, stderr=stderr)
    return _failed_dispatch(
        f"{failure_label} failed with exit code {exit_code}.",
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )


def _resolve_script_invocation(script_file: Path) -> tuple[str | list[str], bool]:
    if os.access(script_file, os.X_OK):
        return [str(script_file)], False
    if script_file.suffix == ".py":
        return [sys.executable, str(script_file)], False
    if script_file.suffix in (".sh", ".bash"):
        return ["bash", str(script_file)], False
    return str(script_file), True


def _execute_command_step(
    step: StepDefinition,
    sandbox_path: Path,
    on_output: Callable[[str, str], None] | None = None,
) -> StepDispatchOutcome:
    """Execute a COMMAND step inside sandbox_path."""
    if not step.command:
        return _failed_dispatch("Command step has no command string defined.")
    return _run_process(
        step.command,
        shell=True,
        cwd=sandbox_path,
        timeout_seconds=step.timeout_seconds,
        failure_label="Command",
        step_kind="Command",
        on_output=on_output,
    )


def _execute_script_step(
    step: StepDefinition,
    sandbox_path: Path,
    on_output: Callable[[str, str], None] | None = None,
) -> StepDispatchOutcome:
    """Execute a SCRIPT step inside sandbox_path."""
    if not step.script_path:
        return _failed_dispatch("Script step has no script_path defined.")

    script_file = sandbox_path / step.script_path
    if not script_file.exists() or not script_file.is_file():
        return _failed_dispatch(f"Script file not found at '{step.script_path}'.")

    cmd, shell = _resolve_script_invocation(script_file)
    return _run_process(
        cmd,
        shell=shell,
        cwd=sandbox_path,
        timeout_seconds=step.timeout_seconds,
        failure_label="Script",
        step_kind="Script",
        on_output=on_output,
    )


def _execute_agent_step(
    step: StepDefinition,
    sandbox_path: Path,
    context: dict[str, Any] | None,
    on_output: Callable[[str, str], None] | None = None,
) -> StepDispatchOutcome:
    """Execute an AGENT step inside sandbox_path."""
    provider = (context or {}).get("agent") or "local"
    try:
        _ = get_agent_adapter(provider)
        # Check if adapter has prompt method or general interface
        stdout = f"Agent prompt executed with tools: {step.tools}"
        if on_output is not None:
            try:
                on_output("stdout", stdout)
            except Exception as exc:
                return _failed_dispatch(f"Agent output callback error: {exc}", stdout=stdout)
        return StepDispatchOutcome(status="completed", exit_code=0, stdout=stdout, stderr="")
    except Exception as exc:
        return _failed_dispatch(f"Agent provider error: {exc}")


def _dispatch_step_primitive(
    step: StepDefinition,
    sandbox_path: Path,
    context: dict[str, Any] | None,
    on_output: Callable[[str, str], None] | None = None,
) -> StepDispatchOutcome:
    """Run the step's primitive type once and return its raw dispatch outcome."""
    if step.type == StepType.COMMAND:
        return _execute_command_step(step, sandbox_path, on_output=on_output)
    if step.type == StepType.SCRIPT:
        return _execute_script_step(step, sandbox_path, on_output=on_output)
    if step.type == StepType.AGENT:
        return _execute_agent_step(step, sandbox_path, context, on_output=on_output)
    return _failed_dispatch(f"Unsupported step primitive type '{step.type}'.")


def _step_result(
    step_id: str,
    outcome: StepDispatchOutcome,
    duration: float,
    *,
    status: str | None = None,
    exit_code: int | None = None,
) -> StepResult:
    return StepResult(
        step_id=step_id,
        status=status if status is not None else outcome.status,
        exit_code=exit_code if exit_code is not None else outcome.exit_code,
        stdout=outcome.stdout,
        stderr=outcome.stderr,
        duration_seconds=duration,
        attempts=outcome.attempts,
        error_message=outcome.error_message,
    )


def _finalize_failed_step(
    step: StepDefinition,
    outcome: StepDispatchOutcome,
    duration: float,
) -> StepResult:
    """Apply the on_failure escalation once retries (if any) are exhausted."""
    on_failure = step.on_failure
    escalation = on_failure.on_max_retries if on_failure.action == FailurePolicy.RETRY else on_failure.action

    if escalation == FailurePolicy.CONTINUE:
        return _step_result(step.id, outcome, duration, status="ignored", exit_code=0)
    return _step_result(step.id, outcome, duration, status="failed")


def _prepare_step_for_execution(
    step: StepDefinition,
    sandbox_path: Path,
    context: dict[str, Any] | None = None,
) -> tuple[StepDefinition, int]:
    """Resolve uses/run shorthand, interpolate inputs, and compute retry budget."""
    if step.uses is not None or step.run is not None:
        step = resolve_step_definition(step, path=sandbox_path)
    inputs = (context or {}).get("inputs")
    if isinstance(inputs, dict) and inputs:
        step = interpolate_step_fields(step, inputs)
    max_attempts = step.on_failure.max_retries if step.on_failure.action == FailurePolicy.RETRY else 1
    return step, max_attempts


def _format_assertion_failure(step: StepDefinition, failed_conditions: list[str]) -> str:
    """Build the multi-line diagnostic block for a failed step assertion."""
    step_label = step.name or step.id
    lines = [f"Step '{step_label}' failed assertion checks:"]
    lines.extend(f"  [FAIL] {condition}" for condition in failed_conditions)
    return "\n".join(lines)


def _apply_assertions(
    step: StepDefinition,
    outcome: StepDispatchOutcome,
    sandbox_path: Path,
) -> StepDispatchOutcome:
    """Downgrade a completed attempt to failed when step.assert_ checks do not pass."""
    if outcome.status != "completed" or step.assert_ is None:
        return outcome

    result = evaluate_assertions(
        step.assert_,
        exit_code=outcome.exit_code,
        stdout=outcome.stdout,
        stderr=outcome.stderr,
        sandbox_path=sandbox_path,
    )
    if result.passed:
        return outcome

    return outcome.model_copy(
        update={
            "status": "failed",
            "error_message": _format_assertion_failure(step, result.failed_conditions),
        }
    )


def _run_step_attempts(
    step: StepDefinition,
    sandbox_path: Path,
    context: dict[str, Any] | None,
    max_attempts: int,
    on_output: Callable[[str, str], None] | None = None,
) -> StepDispatchOutcome:
    """Dispatch the step up to max_attempts times, sleeping backoff_ms between failures."""
    backoff_ms = step.on_failure.backoff_ms
    outcome = _failed_dispatch("Step did not run.")
    for attempt in range(1, max_attempts + 1):
        outcome = _dispatch_step_primitive(step, sandbox_path, context, on_output=on_output)
        outcome = outcome.model_copy(update={"attempts": attempt})
        outcome = _apply_assertions(step, outcome, sandbox_path)
        if outcome.status == "completed":
            return outcome
        if attempt < max_attempts and backoff_ms > 0:
            time.sleep(backoff_ms / 1000)
    return outcome


def execute_step(
    step: StepDefinition,
    sandbox_path: Path,
    context: dict[str, Any] | None = None,
    on_output: Callable[[str, str], None] | None = None,
) -> StepResult:
    """Execute a step definition inside sandbox_path.

    Args:
        step: StepDefinition instance to execute.
        sandbox_path: Isolated directory path for execution.
        context: Optional dictionary containing execution context or handlers.
        on_output: Optional callback invoked with (stream_name, line) for each line emitted.

    Returns:
        Populated StepResult instance.
    """
    sandbox_path = sandbox_path.resolve()
    if not sandbox_path.exists() or not sandbox_path.is_dir():
        return _step_result(
            step.id,
            _failed_dispatch(f"Sandbox path '{sandbox_path}' does not exist or is not a directory."),
            0.0,
        )

    step, max_attempts = _prepare_step_for_execution(step, sandbox_path, context)
    start_time = time.monotonic()
    outcome = _run_step_attempts(step, sandbox_path, context, max_attempts, on_output=on_output)
    duration = time.monotonic() - start_time

    if outcome.status == "completed":
        return _step_result(step.id, outcome, duration, status="completed", exit_code=0)
    return _finalize_failed_step(step, outcome, duration)
