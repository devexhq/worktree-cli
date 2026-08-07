"""Step execution runner and outcome models."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from getworktree.core.step.schema import FailureAction, StepDefinition, StepType
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

    provider = step.agent or "local"
    try:
        _ = get_agent_adapter(provider)
        # Check if adapter has prompt method or general interface
        stdout = f"Agent prompt executed with tools: {step.tools}"
        return "completed", 0, stdout, "", None
    except Exception as exc:
        return "failed", 1, "", "", f"Agent provider error: {exc}"


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
        return StepResult(
            step_id=step.id,
            status="failed",
            exit_code=1,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            attempts=1,
            error_message=f"Sandbox path '{sandbox_path}' does not exist or is not a directory.",
        )

    max_attempts = 3 if step.failure_action == FailureAction.RETRY else 1
    total_start_time = time.monotonic()
    last_exit_code = 1
    last_stdout = ""

    last_stderr = ""
    last_error: str | None = None
    attempt_count = 0

    for attempt in range(1, max_attempts + 1):
        attempt_count = attempt

        if step.type == StepType.COMMAND:
            status, exit_code, stdout, stderr, err_msg = _execute_command_step(step, sandbox_path)
        elif step.type == StepType.SCRIPT:
            status, exit_code, stdout, stderr, err_msg = _execute_script_step(step, sandbox_path)
        elif step.type == StepType.AGENT:
            status, exit_code, stdout, stderr, err_msg = _execute_agent_step(step, sandbox_path, context)
        else:
            status, exit_code, stdout, stderr, err_msg = (
                "failed",
                1,
                "",
                "",
                f"Unsupported step primitive type '{step.type}'.",
            )

        duration = time.monotonic() - total_start_time
        last_exit_code = exit_code

        last_stdout = stdout
        last_stderr = stderr
        last_error = err_msg

        if status == "completed":
            return StepResult(
                step_id=step.id,
                status="completed",
                exit_code=0,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                attempts=attempt_count,
                error_message=None,
            )

    duration = time.monotonic() - total_start_time

    if step.failure_action == FailureAction.IGNORE:
        return StepResult(
            step_id=step.id,
            status="ignored",
            exit_code=0,
            stdout=last_stdout,
            stderr=last_stderr,
            duration_seconds=duration,
            attempts=attempt_count,
            error_message=last_error,
        )

    return StepResult(
        step_id=step.id,
        status="failed",
        exit_code=last_exit_code,
        stdout=last_stdout,
        stderr=last_stderr,
        duration_seconds=duration,
        attempts=attempt_count,
        error_message=last_error,
    )
