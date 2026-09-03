"""ComponentFormatters for run and resume CLI domain objects."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.core.blueprint.models import BlueprintRunResult


def _render_empty_output(data: BlueprintRunResult) -> Any:
    """Render failure panel or empty text when output_items is empty."""
    if not data.ok and data.errors:
        message = "\n".join(data.errors)
        if data.fixes:
            message += "\nFix:\n" + "\n".join(f"- {fix}" for fix in data.fixes)
        return Panel(message, title="Run Failed", border_style="red")
    return Text("")


def _render_output_items(output_items: list[Any]) -> Any:
    """Render one or more output items as Rich Text or Group."""
    if len(output_items) == 1:
        item = output_items[0]
        return Text.from_markup(item) if isinstance(item, str) else item

    renderables: list[Any] = []
    for item in output_items:
        renderables.append(Text.from_markup(item) if isinstance(item, str) else item)
    return Group(*renderables)


class BlueprintRunFormatter(ComponentFormatter[BlueprintRunResult]):
    """Formatter for task and workflow execution results."""

    def to_rich(self, data: BlueprintRunResult) -> Any:
        """Render execution output lines, panels, or failure summaries.

        Args:
            data: Structured result of blueprint execution.

        Returns:
            Rich renderable object (Group, Panel, Text).
        """
        if not data.output_items:
            return _render_empty_output(data)
        return _render_output_items(data.output_items)

    def to_json_serializable(self, data: BlueprintRunResult) -> dict[str, Any]:
        """Convert BlueprintRunResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of blueprint execution.

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
    target.register(BlueprintRunResult, BlueprintRunFormatter())


# Register default run formatters on the central ui_dispatcher
register_run_formatters()
