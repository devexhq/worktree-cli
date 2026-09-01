"""Orchestration logic for ``wt catalog delete`` CLI command."""

from __future__ import annotations

import typer

from worktree.cli.catalog.models import CatalogDeleteCommandOutcome
from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogDeleteResult


def catalog_delete_command(
    context: CliContext,
    sha_or_name: str,
    force: bool = False,
    output_format: str = "terminal",
) -> CatalogDeleteCommandOutcome:
    """Delete a catalog blueprint file and its database index record.

    Args:
        context: CLI context instance.
        sha_or_name: SHA identifier or name of the blueprint to delete.
        force: When True, skip the confirmation prompt.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        CatalogDeleteCommandOutcome indicating deletion status.
    """
    if not force:
        try:
            confirmed = typer.confirm(
                f"Are you sure you want to delete catalog blueprint '{sha_or_name}'?",
                default=False,
            )
        except typer.Abort:
            confirmed = False
        if not confirmed:
            result = CatalogDeleteResult(cancelled=True, errors=["Deletion cancelled."])
            ui_dispatcher.dispatch(result, output_format=output_format)
            return CatalogDeleteCommandOutcome(result=result, item=None, deleted=False, errors=["Deletion cancelled."])

    catalog = Catalog(path=context.cwd, db=context.db.catalog)
    deleted_item = catalog.delete(sha_or_name)
    if deleted_item is None:
        error_message = f"Catalog blueprint '{sha_or_name}' not found."
        result = CatalogDeleteResult(errors=[error_message])
        ui_dispatcher.dispatch(result, output_format=output_format)
        return CatalogDeleteCommandOutcome(result=result, item=None, deleted=False, errors=[error_message])

    result = CatalogDeleteResult(item=deleted_item, deleted=True)
    ui_dispatcher.dispatch(result, output_format=output_format)
    return CatalogDeleteCommandOutcome(result=result, item=deleted_item, deleted=True)
