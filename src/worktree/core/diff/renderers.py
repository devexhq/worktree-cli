"""Rich console renderers for diff operations."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text

from worktree.common.constants import DEFAULT_MAX_DIFF_LINES
from worktree.common.utils import RichOutput, display_path
from worktree.core.diff.models import DiffResult, DiffStatus


def render_not_initialized(errors: list[str], *, output: RichOutput) -> None:
    """Render the not-initialized error panel for diff commands."""
    output.render_not_initialized(
        errors,
        fix_hint="run `wt init` to initialize getworktree",
    )


def render_session_not_found(session_id: str | None, *, output: RichOutput) -> None:
    """Render the session-not-found error panel."""
    if session_id:
        message = (
            f"Session '{session_id}' not found under .worktree/sessions/.\n"
            "Fix:\n"
            "- run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"
        )
    else:
        message = (
            "No loop run sessions found.\n"
            "Fix:\n"
            "- run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"
        )
    output.add_error_panel("Session Not Found", message)


def render_diff_not_found(session_id: str, *, output: RichOutput) -> None:
    """Render the diff-not-found error panel when diff.patch is missing."""
    message = (
        f"Session '{session_id}' has no diff artifact.\n"
        "Fix:\n"
        f"- verify the session generated a diff artifact at .worktree/sessions/{session_id}/diff.patch"
    )
    output.add_error_panel("Diff Not Found", message)


def render_read_failure(message: str, *, output: RichOutput) -> None:
    """Render the read-failure error panel when diff.patch cannot be read."""
    full_message = f"{message}\nFix:\n- check file permissions and that the artifact is readable"
    output.add_error_panel("Read Failure", full_message)


def render_empty_diff(session_id: str, *, output: RichOutput) -> None:
    """Render the single-line empty diff message."""
    output.add_line(f"No changes recorded for session {session_id}.")


def _resolve_diff_rel_path(result: DiffResult, cwd: Path | None) -> str:
    """Resolve display path for diff artifact relative to execution directory."""
    effective_cwd = cwd or Path.cwd()
    if result.artifact_path is not None:
        return display_path(result.artifact_path, effective_cwd)
    if result.session_id:
        return f".worktree/sessions/{result.session_id}/diff.patch"
    return ".worktree/sessions/<session_id>/diff.patch"


def _resolve_max_diff_lines(max_lines: int | None) -> int:
    """Resolve maximum diff line boundary, falling back to default on invalid inputs."""
    if isinstance(max_lines, int) and max_lines > 0:
        return max_lines
    return DEFAULT_MAX_DIFF_LINES


def _render_truncation_notice(
    output: RichOutput,
    session_id: str | None,
    rel_path: str,
    limit: int,
    total_lines: int,
) -> None:
    """Render dim truncation notice block and interaction hints."""
    output.add_spacer()
    output.add_line(Text(f"... [diff truncated: showing {limit} of {total_lines} lines]", style="dim"))
    output.add_line(Text("Hint:", style="dim"))
    sess_cmd = f"wt diff {session_id}" if session_id else "wt diff"
    output.add_line(Text(f"- run `{sess_cmd} --full` to view complete formatted output", style="dim"))
    output.add_line(Text(f"- run `{sess_cmd} --full | less -R` to page through formatted diff", style="dim"))
    output.add_line(Text(f"- run `{sess_cmd} --raw` to output unformatted patch text", style="dim"))
    output.add_line(Text(f"- inspect artifact at {rel_path}", style="dim"))


def render_diff_success(
    result: DiffResult,
    *,
    raw: bool = False,
    full: bool = False,
    max_lines: int | None = None,
    output: RichOutput,
    cwd: Path | None = None,
) -> None:
    """Render formatted syntax-highlighted diff or raw plain text."""
    if raw:
        output.add_line(result.diff_text)
        return

    rel_path = _resolve_diff_rel_path(result, cwd)
    output.add_line(f"Session: {result.session_id} ({rel_path})\n")

    limit = _resolve_max_diff_lines(max_lines)
    diff_lines = result.diff_text.splitlines()
    total_lines = len(diff_lines)
    is_tty = getattr(output.console, "is_terminal", False)
    should_truncate = is_tty and not full and total_lines > limit

    if should_truncate:
        truncated_content = "\n".join(diff_lines[:limit])
        output.add_line(Syntax(truncated_content.rstrip(), "diff", word_wrap=True))
        _render_truncation_notice(output, result.session_id, rel_path, limit, total_lines)
    else:
        output.add_line(Syntax(result.diff_text.rstrip(), "diff", word_wrap=True))


def render_diff(
    result: DiffResult,
    *,
    raw: bool = False,
    full: bool = False,
    max_lines: int | None = None,
    output: RichOutput,
    cwd: Path | None = None,
) -> None:
    """Render diff result to Rich output based on classified status."""
    if result.status == DiffStatus.NOT_INITIALIZED:
        render_not_initialized(result.errors, output=output)
        return

    if result.status == DiffStatus.SESSION_NOT_FOUND:
        render_session_not_found(result.session_id, output=output)
        return

    if result.status == DiffStatus.DIFF_NOT_FOUND:
        render_diff_not_found(result.session_id or "unknown", output=output)
        return

    if result.status == DiffStatus.READ_FAILURE:
        error_msg = result.errors[0] if result.errors else "Failed to read diff artifact."
        render_read_failure(error_msg, output=output)
        return

    if result.status == DiffStatus.EMPTY_DIFF:
        render_empty_diff(result.session_id or "unknown", output=output)
        return

    if result.status == DiffStatus.OK:
        render_diff_success(result, raw=raw, full=full, max_lines=max_lines, output=output, cwd=cwd)
