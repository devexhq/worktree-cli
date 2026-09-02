"""Orchestration logic for ``wt catalog delete`` CLI command."""

from __future__ import annotations

import typer

from worktree.cli.catalog.models import CatalogDeleteCommandOutcome
from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogDeleteResult


def _confirm_delete(sha_or_name: str) -> bool:
    """Prompt user for deletion confirmation."""
    try:
        return typer.confirm(
            f"Are you sure you want to delete catalog blueprint '{sha_or_name}'?",
            default=False,
        )
    except typer.Abort:
        return False


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
    if not force and not _confirm_delete(sha_or_name):
        result = CatalogDeleteResult(cancelled=True, errors=["Deletion cancelled."])
        ui_dispatcher.dispatch(result, output_format=output_format)
        return CatalogDeleteCommandOutcome(
            result=result,
            item=None,
            deleted=False,
            errors=list(result.errors),
        )

    result = Catalog(path=context.cwd, db=context.db.catalog).delete(sha_or_name)
    ui_dispatcher.dispatch(result, output_format=output_format)
    return CatalogDeleteCommandOutcome(
        result=result,
        item=result.item,
        deleted=result.deleted,
        errors=list(result.errors),
    )
