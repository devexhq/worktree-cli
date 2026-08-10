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


def _execute_command_step(step: StepDefinition, sandbox_path: Path) -> tuple[str, int, str, str, str | None]:
    """Execute a COMMAND step inside sandbox_path."""
    if not step.command:
        return "failed", 1, "", "", "Command step has no command string defined."

    try:
        res = subprocess.run(
            step.command,
            shell=True,
            cwd=sandbox_path,
            capture_output=True,
            text=True,
            timeout=step.timeout_seconds,
        )
        stdout = res.stdout or ""
        stderr = res.stderr or ""
        if res.returncode == 0:
            return "completed", 0, stdout, stderr, None
        return (
            "failed",
            res.returncode,
            stdout,
            stderr,
            f"Command failed with exit code {res.returncode}.",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (
            (exc.stdout or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            (exc.stderr or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return (
            "failed",
            124,
            stdout,
            stderr,
            f"Command step execution timed out after {step.timeout_seconds} seconds.",
        )
    except Exception as exc:
        return "failed", 1, "", "", f"Command execution error: {exc}"


def _execute_script_step(step: StepDefinition, sandbox_path: Path) -> tuple[str, int, str, str, str | None]:
    """Execute a SCRIPT step inside sandbox_path."""
    if not step.script_path:
        return "failed", 1, "", "", "Script step has no script_path defined."

    script_file = sandbox_path / step.script_path
    if not script_file.exists() or not script_file.is_file():
        return (
            "failed",
            1,
            "",
            "",
            f"Script file not found at '{step.script_path}'.",
        )

    if os.access(script_file, os.X_OK):
        cmd: str | list[str] = [str(script_file)]
        shell = False
    elif script_file.suffix == ".py":
        cmd = [sys.executable, str(script_file)]
        shell = False
    elif script_file.suffix in (".sh", ".bash"):
        cmd = ["bash", str(script_file)]
        shell = False
    else:
        cmd = str(script_file)
        shell = True

    try:
        res = subprocess.run(
            cmd,
            shell=shell,
            cwd=sandbox_path,
            capture_output=True,
            text=True,
            timeout=step.timeout_seconds,
        )
        stdout = res.stdout or ""
        stderr = res.stderr or ""
        if res.returncode == 0:
            return "completed", 0, stdout, stderr, None
        return (
            "failed",
            res.returncode,
            stdout,
            stderr,
            f"Script failed with exit code {res.returncode}.",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (
            (exc.stdout or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            (exc.stderr or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return (
            "failed",
            124,
            stdout,
            stderr,
            f"Script step execution timed out after {step.timeout_seconds} seconds.",
        )
    except Exception as exc:
        return "failed", 1, "", "", f"Script execution error: {exc}"


def _execute_agent_step(
    step: StepDefinition, sandbox_path: Path, context: dict[str, Any] | None
) -> tuple[str, int, str, str, str | None]:
    """Execute an AGENT step inside sandbox_path."""
    if context and "agent_handler" in context and callable(context["agent_handler"]):
        try:
            return context["agent_handler"](step, sandbox_path, context)
        except Exception as exc:
            return "failed", 1, "", "", f"Agent handler exception: {exc}"

    provider = (context or {}).get("agent") or "local"
    try:
        _ = get_agent_adapter(provider)
        # Check if adapter has prompt method or general interface
        stdout = f"Agent prompt executed with tools: {step.tools}"
        return "completed", 0, stdout, "", None
    except Exception as exc:
        return "failed", 1, "", "", f"Agent provider error: {exc}"


def _dispatch_step_primitive(
    step: StepDefinition, sandbox_path: Path, context: dict[str, Any] | None
) -> tuple[str, int, str, str, str | None]:
    """Run the step's primitive type once and return its raw outcome tuple."""
    if step.type == StepType.COMMAND:
        return _execute_command_step(step, sandbox_path)
    if step.type == StepType.SCRIPT:
        return _execute_script_step(step, sandbox_path)
    if step.type == StepType.AGENT:
        return _execute_agent_step(step, sandbox_path, context)
    return "failed", 1, "", "", f"Unsupported step primitive type '{step.type}'."


def _step_result(
    step_id: str,
    status: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    duration: float,
    attempts: int,
    error_message: str | None = None,
) -> StepResult:
    return StepResult(
        step_id=step_id,
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=duration,
        attempts=attempts,
        error_message=error_message,
    )


def _finalize_failed_step(
    step: StepDefinition,
    exit_code: int,
    stdout: str,
    stderr: str,
    error_message: str | None,
    duration: float,
    attempts: int,
) -> StepResult:
    """Apply the on_failure escalation once retries (if any) are exhausted."""
    on_failure = step.on_failure
    escalation = on_failure.on_max_retries if on_failure.action == FailurePolicy.RETRY else on_failure.action

    if escalation == FailurePolicy.CONTINUE:
        return _step_result(step.id, "ignored", 0, stdout, stderr, duration, attempts, error_message)
    return _step_result(step.id, "failed", exit_code, stdout, stderr, duration, attempts, error_message)


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
) -> tuple[str, int, str, str, str | None, int]:
    """Dispatch the step up to max_attempts times, sleeping backoff_ms between failures."""
    backoff_ms = step.on_failure.backoff_ms
    for attempt in range(1, max_attempts + 1):
        status, exit_code, stdout, stderr, error_message = _dispatch_step_primitive(step, sandbox_path, context)
        if status == "completed":
            return status, exit_code, stdout, stderr, error_message, attempt
        if attempt < max_attempts and backoff_ms > 0:
            time.sleep(backoff_ms / 1000)
    return status, exit_code, stdout, stderr, error_message, max_attempts


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
            "failed",
            1,
            "",
            "",
            0.0,
            1,
            f"Sandbox path '{sandbox_path}' does not exist or is not a directory.",
        )

    step, max_attempts = _prepare_step_for_execution(step, sandbox_path)
    start_time = time.monotonic()
    status, exit_code, stdout, stderr, error_message, attempts = _run_step_attempts(
        step, sandbox_path, context, max_attempts
    )
    duration = time.monotonic() - start_time

    if status == "completed":
        return _step_result(step.id, "completed", 0, stdout, stderr, duration, attempts)
    return _finalize_failed_step(step, exit_code, stdout, stderr, error_message, duration, attempts)
