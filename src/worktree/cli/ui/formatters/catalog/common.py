"""Shared Rich tables for catalog formatters."""

from __future__ import annotations

from rich.table import Table

from worktree.common.utils import enum_value
from worktree.core.db import CatalogRecord


def build_catalog_table(items: list[CatalogRecord]) -> Table:
    """Build the Rich table displaying catalog blueprint items.

    Args:
        items: List of CatalogRecord instances.

    Returns:
        A Rich Table with Name, Type, Path, SHA columns.
    """
    table = Table(title="Catalog Blueprints:", title_justify="left", show_header=True)
    table.add_column("Name")
    table.add_column("Type", no_wrap=True)
    table.add_column("Path")
    table.add_column("SHA", no_wrap=True)

    for item in items:
        t_type = enum_value(item.item_type)
        table.add_row(
            item.name,
            t_type,
            str(item.path),
            item.sha,
        )

    return table


def build_catalog_template_table(rows: list[tuple[str, str]]) -> Table:
    """Build the Rich table displaying packaged `default.yml` templates.

    Args:
        rows: List of (type, relative_path) pairs.

    Returns:
        A Rich Table with TYPE and PATH columns.
    """
    table = Table(title="Catalog Templates:", title_justify="left", show_header=True)
    table.add_column("TYPE", no_wrap=True)
    table.add_column("PATH")

    for item_type, rel_path in rows:
        table.add_row(item_type, rel_path)

    return table
