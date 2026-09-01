"""ComponentFormatters for status CLI domain objects."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from worktree.cli.status.renderers import (
    _collect_all_warnings,
    _collect_remediations,
    build_status_table,
)
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.core.status.models import WorktreeStatusResult


class WorktreeStatusFormatter(ComponentFormatter[WorktreeStatusResult]):
    """Formatter for workspace status results."""

    def to_rich(self, data: WorktreeStatusResult) -> Any:
        """Render Rich table, warnings, and remediations.

        Args:
            data: Unified workspace status collection result.

        Returns:
            Rich renderable object (Table or Group).
        """
        table = build_status_table(data)
        warnings = _collect_all_warnings(data)
        remediations = _collect_remediations(data)

        if not warnings and not remediations:
            return table

        renderables: list[Any] = [table]

        if warnings:
            renderables.append(Text(""))
            renderables.append(Text.from_markup("[yellow]⚠️ Configuration & Context Warnings:[/yellow]"))
            for warning in warnings:
                bullet = Text("  • ", style="dim")
                bullet.append(warning)
                renderables.append(bullet)

        if remediations:
            renderables.append(Text(""))
            renderables.append(Text("Next Steps & Remediation:"))
            for remediation in remediations:
                bullet = Text("  • ", style="dim")
                bullet.append(remediation)
                renderables.append(bullet)

        return Group(*renderables)

    def to_json_serializable(self, data: WorktreeStatusResult) -> dict[str, Any]:
        """Convert WorktreeStatusResult to primitive dictionary for JSON serialization.

        Args:
            data: Unified workspace status collection result.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def register_status_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register all status ComponentFormatter instances on a UiDispatcher.

    Args:
        dispatcher: UiDispatcher instance to register on. Defaults to ui_dispatcher.
    """
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(WorktreeStatusResult, WorktreeStatusFormatter())


# Register default status formatters on the central ui_dispatcher
register_status_formatters()
