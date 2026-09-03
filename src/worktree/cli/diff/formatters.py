"""ComponentFormatters for diff CLI domain objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.constants import DEFAULT_MAX_DIFF_LINES
from worktree.common.types import ComponentFormatter
from worktree.common.utils import display_path
from worktree.core.diff.models import DiffResult, DiffStatus


def _resolve_diff_rel_path(data: DiffResult) -> str:
    """Resolve display path for diff artifact relative to current working directory."""
    if data.artifact_path is not None:
        return display_path(data.artifact_path, Path.cwd())
    if data.session_id:
        return f".worktree/sessions/{data.session_id}/diff.patch"
    return ".worktree/sessions/<session_id>/diff.patch"


def _format_diff_error_panel(data: DiffResult) -> Panel:
    """Format error panel for non-ok diff results."""
    if data.status == DiffStatus.SESSION_NOT_FOUND:
        if data.session_id:
            message = (
                f"Session '{data.session_id}' not found under .worktree/sessions/.\n"
                "Fix:\n"
                "- run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"
            )
        else:
            message = (
                "No loop run sessions found.\n"
                "Fix:\n"
                "- run `wt sandbox list` or check .worktree/sessions/ for valid session IDs"
            )
        return Panel(message, title="Session Not Found", border_style="red")

    if data.status == DiffStatus.DIFF_NOT_FOUND:
        session_label = data.session_id or "unknown"
        message = (
            f"Session '{session_label}' has no diff artifact.\n"
            "Fix:\n"
            f"- verify the session generated a diff artifact at .worktree/sessions/{session_label}/diff.patch"
        )
        return Panel(message, title="Diff Not Found", border_style="red")

    if data.status == DiffStatus.READ_FAILURE:
        error_message = data.errors[0] if data.errors else "Failed to read diff artifact."
        message = f"{error_message}\nFix:\n- check file permissions and that the artifact is readable"
        return Panel(message, title="Read Failure", border_style="red")

    error_message = "\n\n".join(data.errors) if data.errors else "Diff operation failed."
    return Panel(error_message, title="Diff Failed", border_style="red")


def _format_truncation_notice(
    session_id: str | None,
    relative_path: str,
    limit: int,
    total_lines: int,
) -> list[Any]:
    """Render truncation notice and interaction hints."""
    session_command = f"wt diff {session_id}" if session_id else "wt diff"
    return [
        Text(""),
        Text(f"... [diff truncated: showing {limit} of {total_lines} lines]", style="dim"),
        Text("Hint:", style="dim"),
        Text(f"- run `{session_command} --full` to view complete formatted output", style="dim"),
        Text(f"- run `{session_command} --full | less -R` to page through formatted diff", style="dim"),
        Text(f"- run `{session_command} --raw` to output unformatted patch text", style="dim"),
        Text(f"- inspect artifact at {relative_path}", style="dim"),
    ]


class DiffResultFormatter(ComponentFormatter[DiffResult]):
    """Formatter for diff command results."""

    def __init__(
        self,
        *,
        full: bool = False,
        max_lines: int | None = None,
    ) -> None:
        """Initialize DiffResultFormatter with optional truncation overrides.

        Args:
            full: Bypass line truncation limits in interactive terminals.
            max_lines: Custom line truncation threshold for testing.
        """
        self.full = full
        self.max_lines = max_lines

    def to_rich(self, data: DiffResult) -> Any:
        """Render syntax-highlighted unified diff, empty message, or error panel.

        Args:
            data: Structured result of diff retrieval operation.

        Returns:
            Rich renderable object (Group, Text, or Panel).
        """
        if data.status == DiffStatus.EMPTY_DIFF:
            session_label = data.session_id or "unknown"
            return Text(f"No changes recorded for session {session_label}.")

        if not data.ok:
            return _format_diff_error_panel(data)

        relative_path = _resolve_diff_rel_path(data)
        header = Text(f"Session: {data.session_id} ({relative_path})\n")

        limit = self.max_lines if isinstance(self.max_lines, int) and self.max_lines > 0 else DEFAULT_MAX_DIFF_LINES
        diff_lines = data.diff_text.splitlines()
        total_lines = len(diff_lines)
        is_tty = Console().is_terminal
        should_truncate = is_tty and not self.full and total_lines > limit

        if should_truncate:
            truncated_content = "\n".join(diff_lines[:limit])
            syntax = Syntax(truncated_content.rstrip(), "diff", word_wrap=True)
            notice_renderables = _format_truncation_notice(data.session_id, relative_path, limit, total_lines)
            return Group(header, syntax, *notice_renderables)

        syntax = Syntax(data.diff_text.rstrip(), "diff", word_wrap=True)
        return Group(header, syntax)

    def to_json_serializable(self, data: DiffResult) -> dict[str, Any]:
        """Convert DiffResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of diff retrieval operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def register_diff_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register all diff ComponentFormatter instances on a UiDispatcher.

    Args:
        dispatcher: UiDispatcher instance to register on. Defaults to ui_dispatcher.
    """
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(DiffResult, DiffResultFormatter())


# Register default diff formatters on the central ui_dispatcher
register_diff_formatters()
