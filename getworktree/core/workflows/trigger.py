"""Execute workflow trigger commands and capture structured results."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from getworktree.common.fs import atomic_write_json


class TriggerRunStatus(StrEnum):
    """Classified outcomes for running a workflow trigger command."""

    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SPAWN_FAILED = "spawn_failed"
    CWD_MISSING = "cwd_missing"


class TriggerRunResult(BaseModel):
    """Non-raising result of a trigger command execution."""

    model_config = {"extra": "forbid", "strict": True}

    status: TriggerRunStatus
    command: str
    args: list[str]
    cwd: Path
    exit_code: int | None = None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    log_dir: Path | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True only when the trigger exited successfully."""
        return self.status == TriggerRunStatus.PASSED


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _decode_output(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically with UTF-8, preserving exact content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)


def _write_artifacts(result: TriggerRunResult, log_dir: Path) -> list[str]:
    """Persist trigger logs; return warning messages on failure."""
    warnings: list[str] = []
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return [f"Failed to create trigger log_dir '{log_dir}': {exc}"]

    stdout_path = log_dir / "trigger_stdout.log"
    stderr_path = log_dir / "trigger_stderr.log"
    meta_path = log_dir / "trigger_meta.json"
    meta = {
        "command": result.command,
        "args": result.args,
        "cwd": str(result.cwd),
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "status": result.status.value,
        "duration_ms": result.duration_ms,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }
    try:
        _atomic_write_text(stdout_path, result.stdout)
        _atomic_write_text(stderr_path, result.stderr)
        atomic_write_json(meta_path, meta)
    except OSError as exc:
        warnings.append(f"Failed to write trigger artifacts under '{log_dir}': {exc}")
    return warnings


def run_trigger(
    *,
    command: str,
    args: list[str] | None = None,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
    log_dir: Path | None = None,
) -> TriggerRunResult:
    """Run trigger argv in ``cwd``; never raises for classified outcomes.

    Args:
        command: Executable name or path (argv[0]).
        args: Remaining argv entries; defaults to an empty list.
        cwd: Working directory for the process (sandbox path).
        timeout_seconds: Wall-clock timeout (≥ 1).
        env: Full child environment when provided; inherit parent when None.
        log_dir: Optional directory for atomic trigger log artifacts.

    Returns:
        Structured ``TriggerRunResult`` for pass/fail/timeout/spawn/cwd cases.
    """
    argv_args = list(args) if args is not None else []
    cwd_path = cwd.expanduser()
    # Prefer absolute path for stable artifacts/meta without requiring resolve on
    # missing paths (resolve still works for missing on Python 3).
    try:
        cwd_abs = cwd_path.resolve()
    except OSError:
        cwd_abs = cwd_path

    started_at = _now_iso()
    started_mono = time.monotonic()

    if not cwd_abs.is_dir():
        finished_at = _now_iso()
        duration_ms = int((time.monotonic() - started_mono) * 1000)
        result = TriggerRunResult(
            status=TriggerRunStatus.CWD_MISSING,
            command=command,
            args=argv_args,
            cwd=cwd_abs,
            exit_code=None,
            timed_out=False,
            stdout="",
            stderr="",
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
            log_dir=log_dir,
            errors=[
                f"Trigger working directory does not exist: '{cwd_abs}' "
                f"(TRIGGER_CWD_MISSING).\n"
                "Fix:\n"
                "- ensure the sandbox path exists before running the trigger"
            ],
        )
        if log_dir is not None:
            result.warnings.extend(_write_artifacts(result, log_dir))
        return result

    if timeout_seconds < 1:
        # Callers must pass ≥ 1; treat as spawn/config style failure without shell.
        finished_at = _now_iso()
        duration_ms = int((time.monotonic() - started_mono) * 1000)
        result = TriggerRunResult(
            status=TriggerRunStatus.SPAWN_FAILED,
            command=command,
            args=argv_args,
            cwd=cwd_abs,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
            log_dir=log_dir,
            errors=[
                f"Failed to start trigger command '{command}': "
                "timeout_seconds must be an integer >= 1\n"
                "Fix:\n"
                "- ensure the command is installed and on PATH "
                "inside the sandbox environment"
            ],
        )
        if log_dir is not None:
            result.warnings.extend(_write_artifacts(result, log_dir))
        return result

    argv = [command, *argv_args]
    stdout = ""
    stderr = ""
    exit_code: int | None = None
    timed_out = False
    status = TriggerRunStatus.FAILED
    errors: list[str] = []

    try:
        completed = subprocess.run(
            argv,
            cwd=cwd_abs,
            env=env,
            capture_output=True,
            text=False,
            shell=False,
            timeout=timeout_seconds,
            check=False,
        )
        stdout = _decode_output(completed.stdout)
        stderr = _decode_output(completed.stderr)
        exit_code = int(completed.returncode)
        if exit_code == 0:
            status = TriggerRunStatus.PASSED
            errors = []
        else:
            status = TriggerRunStatus.FAILED
            errors = [f"Trigger command '{command}' exited with code {exit_code} (TRIGGER_FAILED)."]
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        status = TriggerRunStatus.TIMEOUT
        stdout = _decode_output(exc.stdout)
        stderr = _decode_output(exc.stderr)
        errors = [
            f"Trigger timed out after {timeout_seconds}s: {command}\n"
            "Fix:\n"
            "- raise trigger.timeout_seconds on the workflow, or\n"
            "- raise workflow.default_trigger_timeout_seconds in .worktree/config.json"
        ]
    except FileNotFoundError as exc:
        status = TriggerRunStatus.SPAWN_FAILED
        errors = [
            f"Failed to start trigger command '{command}': {exc}\n"
            "Fix:\n"
            "- ensure the command is installed and on PATH "
            "inside the sandbox environment"
        ]
    except OSError as exc:
        status = TriggerRunStatus.SPAWN_FAILED
        errors = [
            f"Failed to start trigger command '{command}': {exc}\n"
            "Fix:\n"
            "- ensure the command is installed and on PATH "
            "inside the sandbox environment"
        ]

    finished_at = _now_iso()
    duration_ms = int((time.monotonic() - started_mono) * 1000)
    result = TriggerRunResult(
        status=status,
        command=command,
        args=argv_args,
        cwd=cwd_abs,
        exit_code=exit_code,
        timed_out=timed_out,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        started_at=started_at,
        finished_at=finished_at,
        log_dir=log_dir,
        errors=errors,
    )
    if log_dir is not None:
        result.warnings.extend(_write_artifacts(result, log_dir))
    return result
