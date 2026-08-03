"""Rich-facing formatters for ``wt loop run`` attempt lines and summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from getworktree.core.loops.runner import AttemptRecord, LoopFinalStatus, LoopRunResult

_SUMMARY_RULE = "── Loop run summary ───────────────────────────────────────────"


def exit_code_for_status(status: LoopFinalStatus) -> int:
    """Map final loop status to process exit code (FR-4)."""
    if status == LoopFinalStatus.PASSED:
        return 0
    if status == LoopFinalStatus.FAILED:
        return 1
    if status == LoopFinalStatus.UNFIXABLE:
        return 2
    if status == LoopFinalStatus.ABORTED:
        return 130
    return 1


def _ms_to_seconds_label(duration_ms: int | None) -> str:
    if duration_ms is None:
        return ""
    seconds = duration_ms / 1000.0
    return f" {seconds:.1f}s"


def _format_argv(command: str, args: list[str] | None = None) -> str:
    parts = [command, *(args or [])]
    return " ".join(str(part) for part in parts if str(part))


def format_trigger_line(
    *,
    status: str | None,
    exit_code: int | None = None,
    duration_ms: int | None = None,
) -> str:
    """Format one trigger result line."""
    resolved = status or "unknown"
    if resolved == "passed":
        return f"  Trigger: passed{_ms_to_seconds_label(duration_ms)}"
    exit_part = ""
    if exit_code is not None:
        exit_part = f" (exit {exit_code})"
    return f"  Trigger: {resolved}{exit_part}{_ms_to_seconds_label(duration_ms)}"


def format_agent_line(
    *,
    status: str | None,
    duration_ms: int | None = None,
) -> str | None:
    """Format agent line, or None when agent was not invoked."""
    if status is None:
        return None
    return f"  Agent:   {status}{_ms_to_seconds_label(duration_ms)}"


def format_patch_line(
    *,
    status: str | None,
    touched_files: list[str] | None = None,
) -> str | None:
    """Format patch line, or None when patch was not attempted."""
    if status is None:
        return None
    files = list(touched_files or [])
    if status == "applied" and files:
        n = len(files)
        label = "file" if n == 1 else "files"
        return f"  Patch:   applied ({n} {label})"
    return f"  Patch:   {status}"


def format_attempt_header(*, attempt: int, max_attempts: int) -> str:
    """Return the attempt header line with trailing newline."""
    return f"Attempt {attempt}/{max_attempts}\n"


def format_progress_event(event_name: str, payload: dict[str, Any]) -> str | None:
    """Format one controller event for live CLI progress.

    Returns plain text with a trailing newline, or ``None`` when the event is
    not user-facing.
    """
    if event_name == "session_start":
        loop_name = str(payload.get("loop_name") or "")
        session_id = str(payload.get("session_id") or "")
        max_attempts = payload.get("max_attempts")
        lines = [f"Running loop {loop_name}"]
        if session_id:
            lines.append(f"Session:  {session_id}")
        if max_attempts is not None:
            lines.append(f"Budget:   {max_attempts} attempt(s)")
        return "\n".join(lines) + "\n\n"

    if event_name == "attempt_start":
        attempt = int(payload.get("attempt") or 1)
        max_attempts = int(payload.get("max_attempts") or attempt)
        return format_attempt_header(attempt=attempt, max_attempts=max_attempts)

    if event_name == "trigger_start":
        command = str(payload.get("command") or "")
        args = payload.get("args") or []
        if not isinstance(args, list):
            args = []
        argv = _format_argv(command, [str(a) for a in args])
        if argv:
            return f"  Trigger: running ({argv})...\n"
        return "  Trigger: running...\n"

    if event_name == "trigger":
        return (
            format_trigger_line(
                status=payload.get("status"),
                exit_code=payload.get("exit_code"),
                duration_ms=payload.get("duration_ms"),
            )
            + "\n"
        )

    if event_name == "agent_start":
        provider = str(payload.get("provider") or "agent")
        mode = str(payload.get("mode") or "")
        detail = provider if not mode else f"{provider}/{mode}"
        return f"  Agent:   running ({detail})...\n"

    if event_name == "agent":
        line = format_agent_line(
            status=payload.get("status"),
            duration_ms=payload.get("duration_ms"),
        )
        return None if line is None else line + "\n"

    if event_name == "patch_start":
        return "  Patch:   applying...\n"

    if event_name == "patch":
        touched = payload.get("touched_files") or []
        if not isinstance(touched, list):
            touched = []
        line = format_patch_line(
            status=payload.get("status"),
            touched_files=[str(p) for p in touched],
        )
        return None if line is None else line + "\n"

    return None


def format_attempt_block(record: AttemptRecord, *, max_attempts: int) -> str:
    """Return multi-line attempt section including trailing newline."""
    lines = [f"Attempt {record.attempt}/{max_attempts}"]
    if record.trigger_status is not None:
        lines.append(
            format_trigger_line(
                status=record.trigger_status,
                exit_code=record.trigger_exit_code,
                duration_ms=record.trigger_duration_ms,
            )
        )
    agent_line = format_agent_line(
        status=record.agent_status,
        duration_ms=record.agent_duration_ms,
    )
    if agent_line is not None:
        lines.append(agent_line)
    patch_line = format_patch_line(
        status=record.patch_status,
        touched_files=record.patch_touched_files,
    )
    if patch_line is not None:
        lines.append(patch_line)
    return "\n".join(lines) + "\n"


def format_attempts_section(result: LoopRunResult) -> str:
    """Format all attempt blocks for a completed run."""
    if not result.attempts:
        return ""
    max_attempts = result.max_attempts or len(result.attempts)
    parts = [
        format_attempt_block(rec, max_attempts=max_attempts) for rec in result.attempts
    ]
    return "".join(parts)


def _sandbox_line(result: LoopRunResult, *, cwd: Path) -> str:
    if result.sandbox_retained and result.sandbox_path is not None:
        path = result.sandbox_path
        try:
            display = path.resolve().relative_to(cwd.resolve()).as_posix()
        except ValueError:
            display = path.as_posix()
        return f"Sandbox:    kept at {display}"
    if result.session_id:
        # Prefer canonical relative sandbox path when retained was false
        return "Sandbox:    removed"
    return "Sandbox:    removed"


def _artifacts_line(session_id: str) -> str:
    return f"Artifacts:  .worktree/sessions/{session_id}"


def _next_steps(result: LoopRunResult) -> list[str]:
    sid = result.session_id or "<id>"
    name = result.loop_name
    if result.status == LoopFinalStatus.PASSED:
        return [
            f"- inspect session: wt history show {sid}",
            f"- view diff:       wt diff {sid}",
        ]
    if result.status == LoopFinalStatus.FAILED:
        return [
            f"- inspect session: wt history show {sid}",
            f"- review logs under .worktree/sessions/{sid}",
            f"- re-run: wt loop run {name}",
        ]
    if result.status == LoopFinalStatus.ABORTED:
        return [
            f"- session partially saved: wt history show {sid}",
            "- clean sandboxes if needed: wt prune",
        ]
    if result.status == LoopFinalStatus.UNFIXABLE:
        return [
            f"- inspect session: wt history show {sid}",
            "- adjust loop context/trigger or fix manually",
        ]
    return [f"- inspect session: wt history show {sid}"]


def format_run_summary(result: LoopRunResult, *, cwd: Path | None = None) -> str:
    """Return final summary block with trailing newline (exact labels FR-5)."""
    root = (cwd or Path.cwd()).resolve()
    max_attempts = result.max_attempts or len(result.attempts)
    used = len(result.attempts)
    lines = [
        _SUMMARY_RULE,
        f"Loop:       {result.loop_name}",
        f"Status:     {result.status.value}",
        f"Session:    {result.session_id}",
        f"Attempts:   {used}/{max_attempts}",
        f"Stop:       {result.stop_reason}",
        _sandbox_line(result, cwd=root),
        _artifacts_line(result.session_id),
        "",
        "Next:",
        *_next_steps(result),
    ]
    return "\n".join(lines) + "\n"


def format_run_output(
    result: LoopRunResult,
    *,
    cwd: Path | None = None,
    include_attempts: bool = True,
) -> str:
    """Attempts section + summary for post-run rendering.

    Args:
        result: Completed loop run.
        cwd: Repository root for relative sandbox paths.
        include_attempts: When False, emit only the summary (live progress
            already printed attempt lines during the run).
    """
    summary = format_run_summary(result, cwd=cwd)
    if not include_attempts:
        return summary
    attempts = format_attempts_section(result)
    if attempts:
        return attempts + "\n" + summary
    return summary
