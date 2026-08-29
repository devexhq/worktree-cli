"""Rich console renderers for diff operations."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax

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


def render_diff_success(
    result: DiffResult,
    *,
    raw: bool,
    output: RichOutput,
    cwd: Path | None = None,
) -> None:
    """Render formatted syntax-highlighted diff or raw plain text."""
    if raw:
        output.add_line(result.diff_text)
        return

    effective_cwd = cwd or Path.cwd()
    rel_path = (
        display_path(result.artifact_path, effective_cwd)
        if result.artifact_path is not None
        else f".worktree/sessions/{result.session_id}/diff.patch"
    )
    output.add_line(f"Session: {result.session_id} ({rel_path})\n")
    syntax = Syntax(result.diff_text.rstrip(), "diff", word_wrap=True)
    output.add_line(syntax)


def render_diff(
    result: DiffResult,
    *,
    raw: bool = False,
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
        render_diff_success(result, raw=raw, output=output, cwd=cwd)
