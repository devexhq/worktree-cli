"""ComponentFormatter for CatalogListResult."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.formatters.catalog.common import (
    build_catalog_table,
    build_catalog_template_table,
)
from worktree.common.types import ComponentFormatter
from worktree.core.catalog.models import CatalogListResult


def _render_list_errors(data: CatalogListResult) -> Panel | None:
    if data.errors:
        return Panel("\n".join(data.errors), title="Catalog Filter Error", border_style="red")
    return None


def _render_list_empty(data: CatalogListResult) -> Any:
    renderables: list[Any] = [Text("No catalog blueprints found.")]
    for warning in data.warnings:
        renderables.append(Panel(warning, title="Catalog Scan Warning", border_style="red"))
    return Group(*renderables) if data.warnings else renderables[0]


def _render_list_items(data: CatalogListResult) -> Any:
    table = build_catalog_table(data.items)
    if not data.warnings:
        return table
    renderables: list[Any] = [table]
    for warning in data.warnings:
        renderables.append(Panel(warning, title="Catalog Scan Warning", border_style="red"))
    return Group(*renderables)


class CatalogListFormatter(ComponentFormatter[CatalogListResult]):
    """Formatter for catalog list command results."""

    def to_rich(self, data: CatalogListResult) -> Any:
        """Render catalog blueprint list, templates table, or empty state."""
        error_panel = _render_list_errors(data)
        if error_panel is not None:
            return error_panel

        if data.templates:
            return build_catalog_template_table(data.templates)

        if data.type_filter == "template":
            return Text("No packaged templates found.")

        if not data.items:
            return _render_list_empty(data)

        return _render_list_items(data)

    def to_json_serializable(self, data: CatalogListResult) -> dict[str, Any]:
        """Convert CatalogListResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
