"""ComponentFormatter for CatalogDeleteResult."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.formatters.common import build_error_panel
from worktree.common.types import ComponentFormatter
from worktree.core.catalog.models import CatalogDeleteResult


class CatalogDeleteFormatter(ComponentFormatter[CatalogDeleteResult]):
    """Formatter for catalog delete command results."""

    def to_rich(self, data: CatalogDeleteResult) -> Any:
        """Render single-line deletion confirmation, cancellation, or error panel."""
        if data.cancelled:
            return Text("Deletion cancelled.")

        if data.errors or not data.ok:
            return build_error_panel(
                "Catalog Delete Failed",
                data.errors,
                "Catalog delete failed.",
                data.fixes,
            )

        if data.deleted and data.item is not None:
            return Text(f"Deleted catalog blueprint '{data.item.sha}' ({data.item.path}).")

        return Text("")

    def to_json_serializable(self, data: CatalogDeleteResult) -> dict[str, Any]:
        """Convert CatalogDeleteResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
