"""ComponentFormatter for PrunedItem."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.formatters.sandbox.common import CATEGORY_LABELS
from worktree.common.types import ComponentFormatter
from worktree.core.sandbox.models import PruneAction, PrunedItem


class PrunedItemFormatter(ComponentFormatter[PrunedItem]):
    """Formatter for single pruned resource items."""

    def to_rich(self, data: PrunedItem) -> Text:
        """Render a styled action line for a pruned resource."""
        cat_label = CATEGORY_LABELS.get(data.category, str(data.category.value))

        if data.action == PruneAction.PRUNED:
            if data.reason and ("would prune" in data.reason.lower() or "dry run" in data.reason.lower()):
                verb = "Would prune"
                style = self._STYLE_MAP.get("warning", "yellow")
            else:
                verb = "Pruned"
                style = self._STYLE_MAP.get("success", "green")
        elif data.action == PruneAction.SKIPPED:
            verb = "Skipped"
            style = self._STYLE_MAP.get("warning", "yellow")
        else:
            verb = "Failed to prune"
            style = self._STYLE_MAP.get("error", "red")

        content = f"• {verb} {cat_label}: {data.identifier}"
        if data.error:
            content += f" ({data.error})"

        return Text(content, style=style)

    def to_json_serializable(self, data: PrunedItem) -> dict[str, Any]:
        """Convert PrunedItem to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
