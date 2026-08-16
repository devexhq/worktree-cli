"""Rich table and console renderers for catalog commands."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from rich.table import Table

from getworktree.common.utils import RichOutput, enum_value
from getworktree.core.db import CatalogRecord

_DEFAULT_RICH_OUTPUT = RichOutput()


def build_catalog_table(items: list[CatalogRecord]) -> Table:
    """Build the Rich table displaying catalog blueprint items.

    Args:
        items: List of CatalogRecord instances.

    Returns:
        A Rich Table with SHA, TYPE, NAME / PATH, CHECKSUM columns.
    """
    table = Table(title="Catalog Blueprints:", title_justify="left", show_header=True)
    table.add_column("SHA", no_wrap=True)
    table.add_column("TYPE", no_wrap=True)
    table.add_column("NAME / PATH")
    table.add_column("CHECKSUM", no_wrap=True)

    for item in items:
        t_type = enum_value(item.item_type)
        checksum_disp = f"{item.checksum[:7]}..." if len(item.checksum) > 7 else item.checksum
        table.add_row(
            item.sha,
            t_type,
            str(item.path),
            checksum_disp,
        )

    return table


def render_catalog_list(
    items: list[CatalogRecord],
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render empty state or catalog blueprints table."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not items:
        output.info("No catalog blueprints found.")
    else:
        output.info(build_catalog_table(items))


def render_catalog_create_success(
    item: CatalogRecord,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render blueprint creation confirmation message."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    t_type = enum_value(item.item_type)
    rel_path = Path(".worktree") / "catalog" / item.path
    output.info(f"Created catalog blueprint '{item.sha}' (type: {t_type}) at '{rel_path}'.")


def render_catalog_show(
    item: CatalogRecord,
    content: str,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render detailed catalog blueprint view including definition content."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    t_type = enum_value(item.item_type)
    rel_path = Path(".worktree") / "catalog" / item.path
    output.info(f"[bold green]Blueprint:[/]   {item.name} ({item.sha})")
    output.info(f"[bold green]Type:[/]        {t_type}")
    output.info(f"[bold green]Path:[/]        {rel_path}")
    output.info(f"[bold green]Checksum:[/]    {item.checksum}")
    output.info("\n[bold cyan]Definition:[/]")
    if content:
        output.info(Syntax(content.strip(), "yaml"))


def render_catalog_delete_success(
    item: CatalogRecord,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render blueprint deletion confirmation message."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    output.info(f"Deleted catalog blueprint '{item.sha}' ({item.path}).")


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
    rich_output: RichOutput | None = None,
) -> None:
    """Render the packaged `default.yml` templates table for `wt catalog list --type template`."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not rows:
        output.info("No packaged templates found.")
    else:
        output.info(build_catalog_template_table(rows))


def render_template_show_content(
    rel_path: str,
    content: str,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render the raw YAML content of a matching packaged template."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    output.info(f"[bold green]Template:[/]    {rel_path}")
    output.info("\n[bold cyan]Definition:[/]")
    if content:
        output.info(Syntax(content.strip(), "yaml"))
