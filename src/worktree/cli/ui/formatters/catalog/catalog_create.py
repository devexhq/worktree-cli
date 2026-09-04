"""ComponentFormatter for CatalogCreateResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text

from worktree.cli.ui.formatters.common import build_error_panel
from worktree.common.types import ComponentFormatter
from worktree.common.utils import enum_value
from worktree.core.catalog.models import CatalogCreateResult


class CatalogCreateFormatter(ComponentFormatter[CatalogCreateResult]):
    """Formatter for catalog create command results."""

    def to_rich(self, data: CatalogCreateResult) -> Any:
        """Render blueprint creation confirmation or failure panel."""
        if data.errors or not data.ok or data.item is None:
            return build_error_panel(
                "Catalog Creation Failed",
                data.errors,
                "Catalog creation failed.",
                data.fixes,
            )

        t_type = enum_value(data.item.item_type)
        rel_path = Path(".worktree") / "catalog" / data.item.path
        return Text(f"Created catalog blueprint '{data.item.sha}' (type: {t_type}) at '{rel_path}'.")

    def to_json_serializable(self, data: CatalogCreateResult) -> dict[str, Any]:
        """Convert CatalogCreateResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
