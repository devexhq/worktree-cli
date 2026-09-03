"""ComponentFormatter for WorktreeStatusResult."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from worktree.cli.ui.formatters.status.common import (
    build_status_table,
    collect_all_warnings,
    collect_remediations,
)
from worktree.common.types import ComponentFormatter
from worktree.core.status.models import WorktreeStatusResult


class WorktreeStatusFormatter(ComponentFormatter[WorktreeStatusResult]):
    """Formatter for worktree workspace status results."""

    def to_rich(self, data: WorktreeStatusResult) -> Any:
        """Render status summary table, warnings, and remediation hints."""
        table = build_status_table(data)
        renderables: list[Any] = [table]

        warnings = collect_all_warnings(data)
        if warnings:
            renderables.append(Text(""))
            renderables.append(Text.from_markup("[yellow]⚠️ Configuration & Context Warnings:[/yellow]"))
            for warning in warnings:
                renderables.append(Text.from_markup(f"  [dim]•[/dim] {warning}"))

        remediations = collect_remediations(data)
        if remediations:
            renderables.append(Text(""))
            renderables.append(Text("Next Steps & Remediation:"))
            for remediation in remediations:
                renderables.append(Text.from_markup(f"  [dim]•[/dim] {remediation}"))

        return Group(*renderables) if len(renderables) > 1 else renderables[0]

    def to_json_serializable(self, data: WorktreeStatusResult) -> dict[str, Any]:
        """Convert WorktreeStatusResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
