"""Orchestration logic for ``wt catalog delete`` CLI command."""

from __future__ import annotations

import typer

from worktree.cli.context import CliContext
from worktree.core.catalog import Catalog

from ..models import CatalogDeleteCommandOutcome
from ..renderers import render_catalog_delete_success


def catalog_delete_command(
    context: CliContext,
    sha_or_name: str,
    force: bool = False,
) -> CatalogDeleteCommandOutcome:
    """Delete a catalog blueprint file and its database index record.

    Args:
        sha_or_name: SHA identifier or name of the blueprint to delete.
        force: When True, skip the confirmation prompt.
        context: CLI context instance.

    Returns:
        CatalogDeleteCommandOutcome indicating deletion status.
    """
    output = context.output

    if not force:
        try:
            confirmed = typer.confirm(
                f"Are you sure you want to delete catalog blueprint '{sha_or_name}'?",
                default=False,
            )
        except typer.Abort:
            confirmed = False
        if not confirmed:
            output.add_line("Deletion cancelled.")
            return CatalogDeleteCommandOutcome(item=None, deleted=False, errors=["Deletion cancelled."])

    catalog = Catalog(path=context.cwd, db=context.db.catalog)
    deleted_item = catalog.delete(sha_or_name)
    if deleted_item is None:
        error_message = f"Catalog blueprint '{sha_or_name}' not found."
        output.add_error_panel("Catalog Delete Failed", error_message)
        return CatalogDeleteCommandOutcome(item=None, deleted=False, errors=[error_message])

    render_catalog_delete_success(deleted_item, output=output)
    return CatalogDeleteCommandOutcome(item=deleted_item, deleted=True)
