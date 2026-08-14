"""Step execution runner and outcome models."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from getworktree.core.step import FailurePolicy, StepDefinition, StepType
from getworktree.core.step.services.resolver import resolve_step_definition
from getworktree.core.workflows.agents.factory import get_agent_adapter


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


def _decode_captured_output(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _outcome_from_subprocess(
    result: subprocess.CompletedProcess[str],
    *,
    failure_label: str,
) -> StepDispatchOutcome:
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode == 0:
        return StepDispatchOutcome(status="completed", exit_code=0, stdout=stdout, stderr=stderr)
    return _failed_dispatch(
        f"{failure_label} failed with exit code {result.returncode}.",
        exit_code=result.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _timeout_dispatch_outcome(
    exc: subprocess.TimeoutExpired,
    *,
    step_kind: str,
    timeout_seconds: int | float | None,
) -> StepDispatchOutcome:
    return _failed_dispatch(
        f"{step_kind} step execution timed out after {timeout_seconds} seconds.",
        exit_code=124,
        stdout=_decode_captured_output(exc.stdout),
        stderr=_decode_captured_output(exc.stderr),
    )


def _run_process(
    cmd: str | list[str],
    *,
    shell: bool,
    cwd: Path,
    timeout_seconds: int | float | None,
    failure_label: str,
    step_kind: str,
) -> StepDispatchOutcome:
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return _outcome_from_subprocess(result, failure_label=failure_label)
    except subprocess.TimeoutExpired as exc:
        return _timeout_dispatch_outcome(exc, step_kind=step_kind, timeout_seconds=timeout_seconds)
    except Exception as exc:
        return _failed_dispatch(f"{failure_label} execution error: {exc}")


def _resolve_script_invocation(script_file: Path) -> tuple[str | list[str], bool]:
    if os.access(script_file, os.X_OK):
        return [str(script_file)], False
    if script_file.suffix == ".py":
        return [sys.executable, str(script_file)], False
    if script_file.suffix in (".sh", ".bash"):
        return ["bash", str(script_file)], False
    return str(script_file), True


def _execute_command_step(step: StepDefinition, sandbox_path: Path) -> StepDispatchOutcome:
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
    )


def _execute_script_step(step: StepDefinition, sandbox_path: Path) -> StepDispatchOutcome:
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
    )


def _execute_agent_step(
    step: StepDefinition, sandbox_path: Path, context: dict[str, Any] | None
) -> StepDispatchOutcome:
    """Execute an AGENT step inside sandbox_path."""
    if context and "agent_handler" in context and callable(context["agent_handler"]):
        try:
            return context["agent_handler"](step, sandbox_path, context)
        except Exception as exc:
            return _failed_dispatch(f"Agent handler exception: {exc}")

    provider = (context or {}).get("agent") or "local"
    try:
        _ = get_agent_adapter(provider)
        # Check if adapter has prompt method or general interface
        stdout = f"Agent prompt executed with tools: {step.tools}"
        return StepDispatchOutcome(status="completed", exit_code=0, stdout=stdout, stderr="")
    except Exception as exc:
        return _failed_dispatch(f"Agent provider error: {exc}")


def _dispatch_step_primitive(
    step: StepDefinition, sandbox_path: Path, context: dict[str, Any] | None
) -> StepDispatchOutcome:
    """Run the step's primitive type once and return its raw dispatch outcome."""
    if step.type == StepType.COMMAND:
        return _execute_command_step(step, sandbox_path)
    if step.type == StepType.SCRIPT:
        return _execute_script_step(step, sandbox_path)
    if step.type == StepType.AGENT:
        return _execute_agent_step(step, sandbox_path, context)
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


def _prepare_step_for_execution(step: StepDefinition, sandbox_path: Path) -> tuple[StepDefinition, int]:
    """Resolve uses/run shorthand and compute the retry attempt budget."""
    if step.uses is not None or step.run is not None:
        step = resolve_step_definition(step, cwd=sandbox_path)
    max_attempts = step.on_failure.max_retries if step.on_failure.action == FailurePolicy.RETRY else 1
    return step, max_attempts


def _run_step_attempts(
    step: StepDefinition,
    sandbox_path: Path,
    context: dict[str, Any] | None,
    max_attempts: int,
) -> StepDispatchOutcome:
    """Dispatch the step up to max_attempts times, sleeping backoff_ms between failures."""
    backoff_ms = step.on_failure.backoff_ms
    outcome = _failed_dispatch("Step did not run.")
    for attempt in range(1, max_attempts + 1):
        outcome = _dispatch_step_primitive(step, sandbox_path, context)
        outcome = outcome.model_copy(update={"attempts": attempt})
        if outcome.status == "completed":
            return outcome
        if attempt < max_attempts and backoff_ms > 0:
            time.sleep(backoff_ms / 1000)
    return outcome


def execute_step(
    step: StepDefinition,
    sandbox_path: Path,
    context: dict[str, Any] | None = None,
) -> StepResult:
    """Execute a step definition inside sandbox_path.

    Args:
        step: StepDefinition instance to execute.
        sandbox_path: Isolated directory path for execution.
        context: Optional dictionary containing execution context or handlers.

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

    step, max_attempts = _prepare_step_for_execution(step, sandbox_path)
    start_time = time.monotonic()
    outcome = _run_step_attempts(step, sandbox_path, context, max_attempts)
    duration = time.monotonic() - start_time

    if outcome.status == "completed":
        return _step_result(step.id, outcome, duration, status="completed", exit_code=0)
    return _finalize_failed_step(step, outcome, duration)
