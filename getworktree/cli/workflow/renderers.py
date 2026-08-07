"""Rich-facing formatters for ``wt workflow`` list table, attempt lines, and run summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from getworktree.common.utils import RichOutput
from getworktree.core.db import SandboxRecord, WorkflowRunRecord
from getworktree.core.workflows.patch import summarize_unified_diff
from getworktree.core.workflows.runner import (
    AttemptRecord,
    WorkflowFinalStatus,
    WorkflowRunResult,
)

_DEFAULT_RICH_OUTPUT = RichOutput()
_SUMMARY_RULE = "── Workflow run summary ───────────────────────────────────────────"
# Keep approval prompts readable in a terminal without flooding the scrollback.
DEFAULT_PATCH_PREVIEW_MAX_LINES = 200


def build_recorded_workflows_table(
    workflows: list[WorkflowRunRecord] | list[SandboxRecord],
    *,
    cwd: Path | None = None,
) -> Table:
    """Build the ``Recorded Workflows`` table for workflow list output.

    Args:
        workflows: List of recorded workflow run or sandbox session rows from database.
        cwd: Repository root for relative path display.

    Returns:
        A Rich table with SESSION ID, WORKFLOW NAME, BRANCH, STATUS, STARTED AT columns.
    """
    table = Table(title="Recorded Workflows", show_header=True)
    table.add_column("SESSION ID", style="cyan", no_wrap=True)
    table.add_column("WORKFLOW NAME", no_wrap=True)
    table.add_column("BRANCH", no_wrap=True)
    table.add_column("STATUS")
    table.add_column("STARTED AT", no_wrap=True)

    for row in workflows:
        sid = getattr(row, "session_id", getattr(row, "id", "-"))
        name = getattr(row, "workflow_name", getattr(row, "name", "-")) or "-"
        branch = getattr(row, "branch_name", "-")
        status = row.status.value if hasattr(row.status, "value") else str(row.status)
        started = getattr(row, "started_at", getattr(row, "created_at", "-"))
        table.add_row(
            sid,
            name,
            branch,
            status,
            started,
        )
    return table


def render_workflow_list(
    workflows: list[WorkflowRunRecord] | list[SandboxRecord],
    *,
    cwd: Path | None = None,
    rich_output: RichOutput | None = None,
) -> None:
    """Render empty state or the recorded workflows table."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not workflows:
        output.info("No recorded workflows found.")
    else:
        output.info(build_recorded_workflows_table(workflows, cwd=cwd))


def exit_code_for_status(status: WorkflowFinalStatus) -> int:
    """Map final workflow status to process exit code."""
    if status == WorkflowFinalStatus.PASSED:
        return 0
    if status == WorkflowFinalStatus.FAILED:
        return 1
    if status == WorkflowFinalStatus.UNFIXABLE:
        return 2
    if status == WorkflowFinalStatus.ABORTED:
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


def _style_diff_line(line: str) -> Text:
    """Style one diff body line: file headers bold, hunks cyan, +/- red/green."""
    if line.startswith("+++") or line.startswith("---"):
        return Text(line, style="bold")
    if line.startswith("@@"):
        return Text(line, style="cyan")
    if line.startswith("+"):
        return Text(line, style="green")
    if line.startswith("-"):
        return Text(line, style="red")
    return Text(line)


def build_patch_review_panel(
    unified_diff: str,
    *,
    max_diff_lines: int = DEFAULT_PATCH_PREVIEW_MAX_LINES,
) -> Panel:
    """Build a bordered, colorized patch review panel shown before approval."""
    limit = max(1, int(max_diff_lines))
    touched, additions, deletions = summarize_unified_diff(unified_diff)
    n_files = len(touched)
    file_label = "file" if n_files == 1 else "files"

    body = Text()
    if touched:
        body.append("Files: ", style="bold")
        body.append(", ".join(touched))
    else:
        body.append("Files: (unable to parse file list from diff)", style="italic yellow")
    body.append("\n\n")

    diff_text = (unified_diff or "").replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = diff_text.split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines = raw_lines[:-1]

    if not raw_lines:
        body.append("(empty diff)", style="dim italic")
    else:
        for line in raw_lines[:limit]:
            body.append(_style_diff_line(line))
            body.append("\n")
        if len(raw_lines) > limit:
            omitted = len(raw_lines) - limit
            body.append(f"... ({omitted} more line(s) truncated)", style="dim italic")

    title = f"Proposed patch — {n_files} {file_label}, +{additions}/-{deletions}"
    return Panel(body, title=title, title_align="left", border_style="cyan")


def format_error_lines(errors: list[str]) -> list[str]:
    """Format step error detail as indented continuation lines."""
    lines: list[str] = []
    for err in errors:
        parts = err.splitlines() or [""]
        lines.append(f"  Error:   {parts[0]}")
        for continuation in parts[1:]:
            lines.append(f"           {continuation}")
    return lines


def format_attempt_header(*, attempt: int, max_attempts: int) -> str:
    """Return the attempt header line with trailing newline."""
    return f"Attempt {attempt}/{max_attempts}\n"


def format_progress_event(event_name: str, payload: dict[str, Any]) -> str | None:
    """Format one controller event for live CLI progress."""
    if event_name == "session_start":
        workflow_name = str(payload.get("workflow_name") or "")
        session_id = str(payload.get("session_id") or "")
        max_attempts = payload.get("max_attempts")
        lines = [f"Running workflow {workflow_name}"]
        if session_id:
            lines.append(f"Session:  {session_id}")
        if max_attempts is not None:
            lines.append(f"Budget:   {max_attempts} attempt(s)")
        if payload.get("wip"):
            wip_paths = payload.get("wip_paths") or []
            count = len(wip_paths) if isinstance(wip_paths, list) else 0
            lines.append(f"WIP:      included ({count} path(s))")
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
        errors = [str(e) for e in (payload.get("errors") or [])]
        line = (
            format_trigger_line(
                status=payload.get("status"),
                exit_code=payload.get("exit_code"),
                duration_ms=payload.get("duration_ms"),
            )
            + "\n"
        )
        for err_line in format_error_lines(errors):
            line += err_line + "\n"
        return line

    if event_name == "agent_start":
        provider = str(payload.get("provider") or "agent")
        mode = str(payload.get("mode") or "")
        detail = provider if not mode else f"{provider}/{mode}"
        return f"  Agent:   running ({detail})...\n"

    if event_name == "agent_prompt_dumped":
        path = str(payload.get("path") or "").strip()
        if path:
            return f"  Agent:   prompt dumped to {path}\n"
        return "  Agent:   prompt dumped\n"

    if event_name == "agent_prompt_dump_error":
        errors = [str(e) for e in (payload.get("errors") or [])]
        line = "  Agent:   prompt dump failed"
        for err_line in format_error_lines(errors):
            line += "\n" + err_line
        return line + "\n"

    if event_name == "agent":
        line = format_agent_line(
            status=payload.get("status"),
            duration_ms=payload.get("duration_ms"),
        )
        if line is None:
            return None
        errors = [str(e) for e in (payload.get("errors") or [])]
        for err_line in format_error_lines(errors):
            line += "\n" + err_line
        return line + "\n"

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
        if line is None:
            return None
        errors = [str(e) for e in (payload.get("errors") or [])]
        for err_line in format_error_lines(errors):
            line += "\n" + err_line
        return line + "\n"

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
    lines.extend(format_error_lines(record.errors))
    return "\n".join(lines) + "\n"


def format_attempts_section(result: WorkflowRunResult) -> str:
    """Format all attempt blocks for a completed run."""
    if not result.attempts:
        return ""
    max_attempts = result.max_attempts or len(result.attempts)
    parts = [format_attempt_block(rec, max_attempts=max_attempts) for rec in result.attempts]
    return "".join(parts)


def _sandbox_line(result: WorkflowRunResult, *, cwd: Path) -> str:
    if result.sandbox_retained and result.sandbox_path is not None:
        path = result.sandbox_path
        try:
            display = path.resolve().relative_to(cwd.resolve()).as_posix()
        except ValueError:
            display = path.as_posix()
        return f"Sandbox:    kept at {display}"
    if result.session_id:
        return "Sandbox:    removed"
    return "Sandbox:    removed"


def _artifacts_line(session_id: str) -> str:
    return f"Artifacts:  .worktree/sessions/{session_id}"


def _next_steps(result: WorkflowRunResult) -> list[str]:
    sid = result.session_id or "<id>"
    name = result.workflow_name
    if result.status == WorkflowFinalStatus.PASSED:
        return [
            f"- inspect session: wt history show {sid}",
            f"- view diff:       wt diff {sid}",
        ]
    if result.status == WorkflowFinalStatus.FAILED:
        return [
            f"- inspect session: wt history show {sid}",
            f"- review logs under .worktree/sessions/{sid}",
            f"- re-run: wt workflow run {name}",
        ]
    if result.status == WorkflowFinalStatus.ABORTED:
        return [
            f"- session partially saved: wt history show {sid}",
            "- clean sandboxes if needed: wt prune",
        ]
    if result.status == WorkflowFinalStatus.UNFIXABLE:
        return [
            f"- inspect session: wt history show {sid}",
            "- adjust workflow context/trigger or fix manually",
        ]
    return [f"- inspect session: wt history show {sid}"]


def format_run_summary(result: WorkflowRunResult, *, cwd: Path | None = None) -> str:
    """Return final summary block with trailing newline."""
    root = (cwd or Path.cwd()).resolve()
    max_attempts = result.max_attempts or len(result.attempts)
    used = len(result.attempts)
    lines = [
        _SUMMARY_RULE,
        f"Workflow:   {result.workflow_name}",
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
    result: WorkflowRunResult,
    *,
    cwd: Path | None = None,
    include_attempts: bool = True,
) -> str:
    """Attempts section + summary for post-run rendering."""
    summary = format_run_summary(result, cwd=cwd)
    if not include_attempts:
        return summary
    attempts = format_attempts_section(result)
    if attempts:
        return attempts + "\n" + summary
    return summary
