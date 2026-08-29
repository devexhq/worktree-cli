"""Step execution runner and outcome models."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any

from worktree.core.agents.factory import get_agent_adapter
from worktree.core.inputs import interpolate_step_fields
from worktree.core.step.assertions import evaluate_assertions
from worktree.core.step.models import (
    ExecutionMetadata,
    FailurePolicy,
    PreviousStepMetadata,
    StepDefinition,
    StepDispatchOutcome,
    StepExecutionContext,
    StepResult,
    StepType,
)
from worktree.core.step.services.metadata import build_execution_metadata, metadata_to_env
from worktree.core.step.services.resolver import resolve_step_definition


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


def _int_from_context_or_default(context: dict[str, Any], key: str, default: int) -> int:
    if default != 1 or key not in context:
        return default
    return int(context[key])


class StepExecution:
    """Synchronous executor for a single StepDefinition within a sandbox directory."""

    def __init__(self, metadata: StepExecutionContext) -> None:
        self.step = metadata.step
        self.sandbox_path = metadata.sandbox_path.resolve()
        self.context = metadata.context or {}
        self.on_output = metadata.on_output
        self.step_index = _int_from_context_or_default(self.context, "step_index", metadata.step_index)
        self.initial_attempt = _int_from_context_or_default(self.context, "initial_attempt", metadata.initial_attempt)
        self.iteration_index = _int_from_context_or_default(self.context, "iteration_index", metadata.iteration_index)
        self.identity = metadata.identity or self.context.get("identity")
        raw_steps = metadata.steps or self.context.get("steps")
        self.steps: Sequence[PreviousStepMetadata] = list(raw_steps) if raw_steps else []
        self.previous_step = (
            metadata.previous_step or self.context.get("previous_step") or (self.steps[-1] if self.steps else None)
        )
        self.max_attempts = 1
        self._uninterpolated_step = metadata.step

    def run(self) -> StepResult:
        """Execute the step definition within sandbox_path and return its StepResult."""
        if not self.sandbox_path.exists() or not self.sandbox_path.is_dir():
            outcome = _failed_dispatch(f"Sandbox path '{self.sandbox_path}' does not exist or is not a directory.")
            return _step_result(self.step.id, outcome, 0.0)

        self._prepare()
        start_time = time.monotonic()
        outcome = self._run_attempts()
        duration = time.monotonic() - start_time

        if outcome.status == "completed":
            return _step_result(self.step.id, outcome, duration, status="completed", exit_code=0)
        return self._finalize_failure(outcome, duration)

    def _prepare(self) -> None:
        """Resolve shorthand aliases and compute retry budget."""
        if self.step.uses is not None or self.step.run is not None:
            self.step = resolve_step_definition(self.step, path=self.sandbox_path)
        self._uninterpolated_step = self.step
        self.max_attempts = (
            self.step.on_failure.max_retries if self.step.on_failure.action == FailurePolicy.RETRY else 1
        )

    def _run_attempts(self) -> StepDispatchOutcome:
        """Dispatch primitive up to max_attempts times, sleeping backoff_ms between failures."""
        backoff_ms = self._uninterpolated_step.on_failure.backoff_ms
        outcome = _failed_dispatch("Step did not run.")
        for attempt_offset in range(self.max_attempts):
            attempt = self.initial_attempt + attempt_offset
            metadata = build_execution_metadata(
                self._uninterpolated_step,
                step_index=self.step_index,
                attempt=attempt,
                iteration_index=self.iteration_index,
                identity=self.identity,
                previous_step=self.previous_step,
                steps=self.steps,
            )
            inputs = self.context.get("inputs")
            inputs_dict = inputs if isinstance(inputs, dict) else None
            self.step = interpolate_step_fields(
                self._uninterpolated_step,
                inputs=inputs_dict,
                metadata=metadata,
            )
            outcome = self._dispatch_primitive(metadata)
            outcome = outcome.model_copy(update={"attempts": attempt})
            outcome = self._apply_assertions(outcome)
            if outcome.status == "completed":
                return outcome
            if attempt_offset < self.max_attempts - 1 and backoff_ms > 0:
                time.sleep(backoff_ms / 1000)
        return outcome

    def _dispatch_primitive(self, metadata: ExecutionMetadata) -> StepDispatchOutcome:
        """Run the step's primitive type once and return its dispatch outcome."""
        if self.step.type == StepType.COMMAND:
            return self._execute_command(metadata)
        if self.step.type == StepType.SCRIPT:
            return self._execute_script(metadata)
        if self.step.type == StepType.AGENT:
            return self._execute_agent()
        return _failed_dispatch(f"Unsupported step primitive type '{self.step.type}'.")

    def _execute_command(self, metadata: ExecutionMetadata) -> StepDispatchOutcome:
        """Execute a COMMAND step inside sandbox_path."""
        if not self.step.command:
            return _failed_dispatch("Command step has no command string defined.")
        return self._run_process(
            self.step.command,
            shell=True,
            timeout_seconds=self.step.timeout_seconds,
            failure_label="Command",
            step_kind="Command",
            metadata=metadata,
        )

    def _execute_script(self, metadata: ExecutionMetadata) -> StepDispatchOutcome:
        """Execute a SCRIPT step inside sandbox_path."""
        if not self.step.script_path:
            return _failed_dispatch("Script step has no script_path defined.")

        script_file = self.sandbox_path / self.step.script_path
        if not script_file.exists() or not script_file.is_file():
            return _failed_dispatch(f"Script file not found at '{self.step.script_path}'.")

        cmd, shell = _resolve_script_invocation(script_file)
        return self._run_process(
            cmd,
            shell=shell,
            timeout_seconds=self.step.timeout_seconds,
            failure_label="Script",
            step_kind="Script",
            metadata=metadata,
        )

    def _execute_agent(self) -> StepDispatchOutcome:
        """Execute an AGENT step inside sandbox_path."""
        provider = self.context.get("agent") or "local"
        try:
            _ = get_agent_adapter(provider)
            stdout = f"Agent prompt executed with tools: {self.step.tools}"
            if self.on_output is not None:
                try:
                    self.on_output("stdout", stdout)
                except Exception as exc:
                    return _failed_dispatch(f"Agent output callback error: {exc}", stdout=stdout)
            return StepDispatchOutcome(status="completed", exit_code=0, stdout=stdout, stderr="")
        except Exception as exc:
            return _failed_dispatch(f"Agent provider error: {exc}")

    def _build_process_env(self, metadata: ExecutionMetadata) -> dict[str, str]:
        """Merge environment variables: explicit step env > WT_* metadata > ambient env."""
        process_env = os.environ.copy()
        process_env.update(metadata_to_env(metadata))
        process_env.update(self.step.env)
        return process_env

    def _dispatch_pipe_line(
        self,
        line: str,
        stream_name: str,
        collected_lines: list[str],
        collected_errors: list[str],
    ) -> None:
        collected_lines.append(line)
        if self.on_output is not None:
            try:
                self.on_output(stream_name, line)
            except Exception as exc:
                collected_errors.append(f"Output callback error on {stream_name}: {exc}")

    def _stream_pipe(
        self,
        pipe: IO[str] | None,
        stream_name: str,
        collected_lines: list[str],
        collected_errors: list[str],
    ) -> None:
        """Read lines from pipe, accumulate them, and invoke on_output callback."""
        if pipe is None:
            return
        try:
            for line in iter(pipe.readline, ""):
                self._dispatch_pipe_line(line, stream_name, collected_lines, collected_errors)
        except Exception as exc:
            collected_errors.append(f"Failed reading {stream_name} stream: {exc}")
        finally:
            try:
                pipe.close()
            except Exception:
                # Best-effort cleanup: closing stream pipe during termination.
                pass

    def _terminate_process_tree(self, proc: subprocess.Popen[str]) -> None:
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

    def _run_process(
        self,
        cmd: str | list[str],
        *,
        shell: bool,
        timeout_seconds: int | float | None,
        failure_label: str,
        step_kind: str,
        metadata: ExecutionMetadata,
    ) -> StepDispatchOutcome:
        env = self._build_process_env(metadata)
        try:
            proc = subprocess.Popen(
                cmd,
                shell=shell,
                cwd=self.sandbox_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=(sys.platform != "win32"),
                env=env,
            )
        except Exception as exc:
            return _failed_dispatch(f"{failure_label} execution error: {exc}")

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        pipe_errors: list[str] = []

        t_out = threading.Thread(
            target=self._stream_pipe,
            args=(proc.stdout, "stdout", stdout_lines, pipe_errors),
            daemon=True,
        )
        t_err = threading.Thread(
            target=self._stream_pipe,
            args=(proc.stderr, "stderr", stderr_lines, pipe_errors),
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
            self._terminate_process_tree(proc)
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

    def _apply_assertions(self, outcome: StepDispatchOutcome) -> StepDispatchOutcome:
        """Downgrade a completed attempt to failed when step.assert_ checks do not pass."""
        if outcome.status != "completed" or self.step.assert_ is None:
            return outcome

        result = evaluate_assertions(
            self.step.assert_,
            exit_code=outcome.exit_code,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            sandbox_path=self.sandbox_path,
        )
        if result.passed:
            return outcome

        return outcome.model_copy(
            update={
                "status": "failed",
                "error_message": _format_assertion_failure(self.step, result.failed_conditions),
            }
        )

    def _finalize_failure(self, outcome: StepDispatchOutcome, duration: float) -> StepResult:
        """Apply the on_failure escalation once retries (if any) are exhausted."""
        on_failure = self._uninterpolated_step.on_failure
        escalation = on_failure.on_max_retries if on_failure.action == FailurePolicy.RETRY else on_failure.action

        if escalation == FailurePolicy.CONTINUE:
            return _step_result(self.step.id, outcome, duration, status="ignored", exit_code=0)
        return _step_result(self.step.id, outcome, duration, status="failed")


def _resolve_script_invocation(script_file: Path) -> tuple[str | list[str], bool]:
    if os.access(script_file, os.X_OK):
        return [str(script_file)], False
    if script_file.suffix == ".py":
        return [sys.executable, str(script_file)], False
    if script_file.suffix in (".sh", ".bash"):
        return ["bash", str(script_file)], False
    return str(script_file), True


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


def _format_assertion_failure(step: StepDefinition, failed_conditions: list[str]) -> str:
    """Build the multi-line diagnostic block for a failed step assertion."""
    step_label = step.name or step.id
    lines = [f"Step '{step_label}' failed assertion checks:"]
    lines.extend(f"  [FAIL] {condition}" for condition in failed_conditions)
    return "\n".join(lines)
