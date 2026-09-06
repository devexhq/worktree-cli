"""Shared Rich tables for catalog formatters."""

from __future__ import annotations

from rich.table import Table

from worktree.cli.ui.formatters.catalog.catalog_views import (
    CatalogItemView,
    CatalogTemplateView,
)


def build_catalog_table(items: list[CatalogItemView]) -> Table:
    """Build the Rich table displaying catalog blueprint items.

    Args:
        items: List of CatalogItemView instances.

    Returns:
        A Rich Table with Name, Type, Path, SHA columns.
    """
    table = Table(title="Catalog Blueprints:", title_justify="left", show_header=True)
    table.add_column("Name")
    table.add_column("Type", no_wrap=True)
    table.add_column("Path")
    table.add_column("SHA", no_wrap=True)

    for item in items:
        table.add_row(
            item.name,
            item.item_type,
            item.path,
            item.sha,
        )

    return table


def build_catalog_template_table(templates: list[CatalogTemplateView]) -> Table:
    """Build the Rich table displaying packaged `default.yml` templates.

    Args:
        templates: List of CatalogTemplateView instances.

    Returns:
        A Rich Table with TYPE and PATH columns.
    """
    table = Table(title="Catalog Templates:", title_justify="left", show_header=True)
    table.add_column("TYPE", no_wrap=True)
    table.add_column("PATH")

    for template in templates:
        table.add_row(template.item_type, template.path)

    return table
