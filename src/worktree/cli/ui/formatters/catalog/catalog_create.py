"""ComponentFormatter for CatalogCreateResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.text import Text

from worktree.common.types import ComponentFormatter
from worktree.common.utils import enum_value
from worktree.core.catalog.models import CatalogCreateResult


class CatalogCreateFormatter(ComponentFormatter[CatalogCreateResult]):
    """Formatter for catalog create command results."""

    def to_rich(self, data: CatalogCreateResult) -> Any:
        """Render blueprint creation confirmation or failure panel."""
        if data.errors or not data.ok or data.item is None:
            error_message = "\n\n".join(data.errors) if data.errors else "Catalog creation failed."
            if data.fixes:
                error_message += "\nFix:\n" + "\n".join(f"- {fix}" for fix in data.fixes)
            return Panel(error_message, title="Catalog Creation Failed", border_style="red")

        t_type = enum_value(data.item.item_type)
        rel_path = Path(".worktree") / "catalog" / data.item.path
        return Text(f"Created catalog blueprint '{data.item.sha}' (type: {t_type}) at '{rel_path}'.")

    def to_json_serializable(self, data: CatalogCreateResult) -> dict[str, Any]:
        """Convert CatalogCreateResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
