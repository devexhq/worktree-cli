"""ComponentFormatter for HistoryShowResult."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.formatters.history.common import (
    build_checkpoint_renderables,
    build_metadata_table,
)
from worktree.common.types import ComponentFormatter
from worktree.core.db import RunRecord
from worktree.core.history.models import HistoryShowResult, HistoryShowStatus


def _render_show_not_found(session_id: str | None, fixes: list[str] | None = None) -> Panel:
    """Render error panel when requested session record is not found."""
    session_label = session_id or "unknown"
    fix_list = fixes or ["Run `wt history` to view past sessions"]
    message = f"Session '{session_label}' not found.\nFix:\n" + "\n".join(f"- {f}" for f in fix_list)
    return Panel(message, title="Session Not Found", border_style="red")


def _render_show_error(errors: list[str], fixes: list[str] | None = None) -> Panel:
    """Render error panel when session show encounters errors."""
    parts = ["\n\n".join(errors)]
    if fixes:
        parts.append("Fix:\n" + "\n".join(f"- {f}" for f in fixes))
    return Panel("\n".join(parts), title="Session Show Failed", border_style="red")


def _render_show_error_panel(data: HistoryShowResult) -> Panel | None:
    """Check and render error panels for session show operation."""
    if data.status == HistoryShowStatus.NOT_FOUND or (data.run is None and not data.errors):
        return _render_show_not_found(data.session_id, data.fixes)

    if data.errors and not data.ok:
        return _render_show_error(data.errors, data.fixes)

    return None


def _render_show_run(run: RunRecord) -> Any:
    """Render detailed session metadata panel, error panel, and step timeline."""
    renderables: list[Any] = [
        Panel(
            build_metadata_table(run),
            title=f"Session Metadata: {run.session_id}",
            border_style="blue",
        )
    ]

    if run.error_message:
        renderables.append(Panel(run.error_message, title="Error Details", border_style="red"))

    if run.checkpoint_json:
        renderables.extend(build_checkpoint_renderables(run.checkpoint_json))

    return Group(*renderables) if len(renderables) > 1 else renderables[0]


class HistoryShowFormatter(ComponentFormatter[HistoryShowResult]):
    """Formatter for history show command results."""

    def to_rich(self, data: HistoryShowResult) -> Any:
        """Render detailed session metadata panel, error panel, and step timeline."""
        error_panel = _render_show_error_panel(data)
        if error_panel is not None:
            return error_panel

        if data.run is not None:
            return _render_show_run(data.run)

        return Text("")

    def to_json_serializable(self, data: HistoryShowResult) -> dict[str, Any]:
        """Convert HistoryShowResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
