"""ComponentFormatter for HistoryListResult."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from worktree.cli.ui.formatters.common import build_error_panel
from worktree.cli.ui.formatters.history.common import build_history_table
from worktree.common.types import ComponentFormatter
from worktree.core.history.models import HistoryListResult


def _render_list_runs(data: HistoryListResult) -> Any:
    """Render execution history runs table or empty text alongside optional warnings."""
    content: Any = build_history_table(data.runs) if data.runs else Text("No execution history found.")
    if not data.warnings:
        return content

    renderables: list[Any] = []
    for warning in data.warnings:
        renderables.append(Text.from_markup(f"[yellow]Warning:[/] {warning}"))
    renderables.append(content)
    return Group(*renderables)


class HistoryListFormatter(ComponentFormatter[HistoryListResult]):
    """Formatter for history list command results."""

    def to_rich(self, data: HistoryListResult) -> Any:
        """Render execution history table, warnings, or empty state."""
        if not data.ok and data.errors:
            return build_error_panel("History List Failed", data.errors, fixes=data.fixes)

        return _render_list_runs(data)

    def to_json_serializable(self, data: HistoryListResult) -> dict[str, Any]:
        """Convert HistoryListResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
