"""Rich table and console renderers for catalog commands."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from rich.table import Table

from worktree.common.utils import RichOutput, enum_value
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


def render_catalog_list(
    items: list[CatalogRecord],
    *,
    output: RichOutput,
) -> None:
    """Render empty state or catalog blueprints table."""
    if not items:
        output.add_line("No catalog blueprints found.")
    else:
        output.add_line(build_catalog_table(items))


def render_catalog_create_success(
    item: CatalogRecord,
    *,
    output: RichOutput,
) -> None:
    """Render blueprint creation confirmation message."""
    t_type = enum_value(item.item_type)
    rel_path = Path(".worktree") / "catalog" / item.path
    output.add_line(f"Created catalog blueprint '{item.sha}' (type: {t_type}) at '{rel_path}'.")


def render_catalog_show(
    item: CatalogRecord,
    content: str,
    *,
    output: RichOutput,
) -> None:
    """Render detailed catalog blueprint view including definition content."""
    t_type = enum_value(item.item_type)
    rel_path = Path(".worktree") / "catalog" / item.path
    output.add_line(f"[bold green]Blueprint:[/]   {item.name} ({item.sha})")
    output.add_line(f"[bold green]Type:[/]        {t_type}")
    output.add_line(f"[bold green]Path:[/]        {rel_path}")
    output.add_line(f"[bold green]Checksum:[/]    {item.checksum}")
    output.add_line("\n[bold cyan]Definition:[/]")
    if content:
        output.add_line(Syntax(content.strip(), "yaml"))


def render_catalog_delete_success(
    item: CatalogRecord,
    *,
    output: RichOutput,
) -> None:
    """Render blueprint deletion confirmation message."""
    output.add_line(f"Deleted catalog blueprint '{item.sha}' ({item.path}).")


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


def render_catalog_template_list(
    rows: list[tuple[str, str]],
    *,
    output: RichOutput,
) -> None:
    """Render the packaged `default.yml` templates table for `wt catalog list --type template`."""
    if not rows:
        output.add_line("No packaged templates found.")
    else:
        output.add_line(build_catalog_template_table(rows))


def render_template_show_content(
    rel_path: str,
    content: str,
    *,
    output: RichOutput,
) -> None:
    """Render the raw YAML content of a matching packaged template."""
    output.add_line(f"[bold green]Template:[/]    {rel_path}")
    output.add_line("\n[bold cyan]Definition:[/]")
    if content:
        output.add_line(Syntax(content.strip(), "yaml"))
