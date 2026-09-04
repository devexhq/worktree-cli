"""ComponentFormatter for SandboxPruneResult."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from worktree.cli.ui.formatters.sandbox.pruned_item import PrunedItemFormatter
from worktree.common.types import ComponentFormatter
from worktree.core.sandbox.models import SandboxPruneResult


def _format_prune_rich(data: SandboxPruneResult) -> Any:
    """Render rich group or text for sandbox prune result."""
    if not data.items and not data.errors:
        return Text("No stale sandboxes found.")

    renderables: list[Any] = []
    item_formatter = PrunedItemFormatter()
    for item in data.items:
        renderables.append(item_formatter.to_rich(item))

    if data.errors:
        for err in data.errors:
            renderables.append(Text(f"Error: {err}", style="red"))

    return Group(*renderables)


class SandboxPruneFormatter(ComponentFormatter[SandboxPruneResult]):
    """Formatter for sandbox prune command results."""

    def to_rich(self, data: SandboxPruneResult) -> Any:
        """Render sandbox prune action lines, empty state, or errors."""
        return _format_prune_rich(data)

    def to_json_serializable(self, data: SandboxPruneResult) -> dict[str, Any]:
        """Convert SandboxPruneResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
