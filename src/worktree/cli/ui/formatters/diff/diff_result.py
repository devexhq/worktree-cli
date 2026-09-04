"""ComponentFormatter for DiffResult."""

from __future__ import annotations

from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from worktree.cli.ui.formatters.common import build_error_panel
from worktree.cli.ui.formatters.diff.common import format_truncation_notice, resolve_diff_rel_path
from worktree.common.constants import DEFAULT_MAX_DIFF_LINES
from worktree.common.types import ComponentFormatter
from worktree.core.diff.models import DiffResult, DiffStatus


def _format_session_not_found_panel(data: DiffResult, *, raw: bool = False) -> Panel | str:
    """Format error panel when session is missing."""
    default = (
        f"Session '{data.session_id}' not found under .worktree/sessions/."
        if data.session_id
        else "No loop run sessions found."
    )
    fixes = data.fixes or ["Run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"]
    return build_error_panel("Session Not Found", data.errors, default, fixes, raw=raw)


def _format_diff_not_found_panel(data: DiffResult, raw: bool = False) -> Panel | str:
    """Format error panel when diff artifact is missing."""
    session_label = data.session_id or "unknown"
    default = f"Session '{session_label}' has no diff artifact."
    fixes = data.fixes or [
        f"Verify the session generated a diff artifact at .worktree/sessions/{session_label}/diff.patch"
    ]
    return build_error_panel("Diff Not Found", data.errors, default, fixes, raw=raw)


def _format_read_failure_panel(data: DiffResult, raw: bool = False) -> Panel | str:
    """Format error panel when diff artifact cannot be read."""
    fixes = data.fixes or ["Check file permissions and that the artifact is readable"]
    return build_error_panel("Read Failure", data.errors, "Failed to read diff artifact.", fixes, raw=raw)


def _format_diff_error_panel(data: DiffResult, *, raw: bool = False) -> Panel | str:
    """Format error panel for non-ok diff results."""
    if data.status == DiffStatus.SESSION_NOT_FOUND:
        return _format_session_not_found_panel(data, raw=raw)
    if data.status == DiffStatus.DIFF_NOT_FOUND:
        return _format_diff_not_found_panel(data, raw=raw)
    if data.status == DiffStatus.READ_FAILURE:
        return _format_read_failure_panel(data, raw=raw)

    return build_error_panel("Diff Failed", data.errors, "Diff operation failed.", data.fixes)


class DiffResultFormatter(ComponentFormatter[DiffResult]):
    """Formatter for diff command results."""

    def __init__(
        self,
        *,
        full: bool = False,
        max_lines: int | None = None,
    ) -> None:
        """Initialize DiffResultFormatter with optional truncation overrides."""
        self.full = full
        self.max_lines = max_lines

    def to_raw(self, data: DiffResult) -> str:
        """Render a raw diff, empty message or error panel."""
        if data.status == DiffStatus.EMPTY_DIFF:
            session_label = data.session_id or "unknown"
            return f"No changes recorded for session {session_label}."

        if not data.ok:
            return str(_format_diff_error_panel(data, raw=True))

        if data.raw:
            return data.diff_text

        effective_max = data.max_lines if data.max_lines is not None else self.max_lines
        effective_full = data.full or self.full

        limit = effective_max if isinstance(effective_max, int) and effective_max > 0 else DEFAULT_MAX_DIFF_LINES
        diff_lines = data.diff_text.splitlines()
        total_lines = len(diff_lines)
        is_tty = Console().is_terminal
        should_truncate = is_tty and not effective_full and total_lines > limit

        if should_truncate:
            truncated_content = "\n".join(diff_lines[:limit])
            return truncated_content

        return data.diff_text.rstrip()

    def to_rich(self, data: DiffResult) -> Any:
        """Render syntax-highlighted unified diff, empty message, or error panel."""
        if data.status == DiffStatus.EMPTY_DIFF:
            session_label = data.session_id or "unknown"
            return Text(f"No changes recorded for session {session_label}.")

        if not data.ok:
            return _format_diff_error_panel(data)

        if data.raw:
            return Text(data.diff_text)

        relative_path = resolve_diff_rel_path(data)
        header = Text(f"Session: {data.session_id} ({relative_path})\n")

        effective_max = data.max_lines if data.max_lines is not None else self.max_lines
        effective_full = data.full or self.full

        limit = effective_max if isinstance(effective_max, int) and effective_max > 0 else DEFAULT_MAX_DIFF_LINES
        diff_lines = data.diff_text.splitlines()
        total_lines = len(diff_lines)
        is_tty = Console().is_terminal
        should_truncate = is_tty and not effective_full and total_lines > limit

        if should_truncate:
            truncated_content = "\n".join(diff_lines[:limit])
            syntax = Syntax(truncated_content.rstrip(), "diff", word_wrap=True)
            notice_renderables = format_truncation_notice(data.session_id, relative_path, limit, total_lines)
            return Group(header, syntax, *notice_renderables)

        syntax = Syntax(data.diff_text.rstrip(), "diff", word_wrap=True)
        return Group(header, syntax)

    def to_json_serializable(self, data: DiffResult) -> dict[str, Any]:
        """Convert DiffResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
