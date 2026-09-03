"""ComponentFormatters for run and resume CLI domain objects."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.core.blueprint.models import BlueprintRunCommandOutcome


class BlueprintRunFormatter(ComponentFormatter[BlueprintRunCommandOutcome]):
    """Formatter for task and workflow execution outcomes."""

    def to_rich(self, data: BlueprintRunCommandOutcome) -> Any:
        """Render execution output lines, panels, or failure summaries.

        Args:
            data: Structured outcome of blueprint execution.

        Returns:
            Rich renderable object (Group, Panel, Text).
        """
        if not data.output_items:
            if not data.ok and data.errors:
                return Panel("\n".join(data.errors), title="Run Failed", border_style="red")
            return Text("")

        if len(data.output_items) == 1:
            item = data.output_items[0]
            return Text.from_markup(item) if isinstance(item, str) else item

        renderables: list[Any] = []
        for item in data.output_items:
            renderables.append(Text.from_markup(item) if isinstance(item, str) else item)
        return Group(*renderables)

    def to_json_serializable(self, data: BlueprintRunCommandOutcome) -> dict[str, Any]:
        """Convert BlueprintRunCommandOutcome to primitive dictionary for JSON serialization.

        Args:
            data: Structured outcome of blueprint execution.

        Returns:
            JSON-serializable dictionary.
        """
        return {
            "ok": data.ok,
            "run_record": data.run_record.model_dump(mode="json") if data.run_record is not None else None,
            "errors": data.errors,
            "warnings": data.warnings,
            "output_items": [str(item) for item in data.output_items],
        }


def register_run_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register run ComponentFormatter instances on a UiDispatcher.

    Args:
        dispatcher: UiDispatcher instance to register on. Defaults to ui_dispatcher.
    """
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(BlueprintRunCommandOutcome, BlueprintRunFormatter())


# Register default run formatters on the central ui_dispatcher
register_run_formatters()
