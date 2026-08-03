"""Rich-facing formatters for ``wt loop run`` attempt lines and summary."""

from __future__ import annotations

from pathlib import Path

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


def format_trigger_line(record: AttemptRecord) -> str:
    """Format one trigger result line for an attempt block."""
    status = record.trigger_status or "unknown"
    if status == "passed":
        return f"  Trigger: passed{_ms_to_seconds_label(record.trigger_duration_ms)}"
    exit_part = ""
    if record.trigger_exit_code is not None:
        exit_part = f" (exit {record.trigger_exit_code})"
    return (
        f"  Trigger: {status}{exit_part}"
        f"{_ms_to_seconds_label(record.trigger_duration_ms)}"
    )


def format_agent_line(record: AttemptRecord) -> str | None:
    """Format agent line, or None when agent was not invoked."""
    if record.agent_status is None:
        return None
    return (
        f"  Agent:   {record.agent_status}"
        f"{_ms_to_seconds_label(record.agent_duration_ms)}"
    )


def format_patch_line(record: AttemptRecord) -> str | None:
    """Format patch line, or None when patch was not attempted."""
    if record.patch_status is None:
        return None
    status = record.patch_status
    if status == "applied" and record.patch_touched_files:
        n = len(record.patch_touched_files)
        files = "file" if n == 1 else "files"
        return f"  Patch:   applied ({n} {files})"
    return f"  Patch:   {status}"


def format_attempt_block(record: AttemptRecord, *, max_attempts: int) -> str:
    """Return multi-line attempt section including trailing newline."""
    lines = [f"Attempt {record.attempt}/{max_attempts}"]
    if record.trigger_status is not None:
        lines.append(format_trigger_line(record))
    agent_line = format_agent_line(record)
    if agent_line is not None:
        lines.append(agent_line)
    patch_line = format_patch_line(record)
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


def format_run_output(result: LoopRunResult, *, cwd: Path | None = None) -> str:
    """Attempts section + summary for post-run rendering."""
    attempts = format_attempts_section(result)
    summary = format_run_summary(result, cwd=cwd)
    if attempts:
        return attempts + "\n" + summary
    return summary
