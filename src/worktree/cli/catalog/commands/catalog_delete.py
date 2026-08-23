"""Orchestration logic for ``wt catalog delete`` CLI command."""

from __future__ import annotations

import typer

from worktree.common.utils import RichOutput
from worktree.core.catalog.services.inventory import delete_catalog_item_by_sha_or_name
from worktree.core.config.models import CliContext

from ..models import CatalogDeleteCommandOutcome
from ..renderers import render_catalog_delete_success

_DEFAULT_RICH_OUTPUT = RichOutput()


def catalog_delete_command(
    sha_or_name: str,
    force: bool = False,
    *,
    cli_ctx: CliContext,
    rich_output: RichOutput | None = None,
) -> CatalogDeleteCommandOutcome:
    """Delete a catalog blueprint file and its database index record.

    Args:
        sha_or_name: SHA identifier or name of the blueprint to delete.
        force: When True, skip the confirmation prompt.
        cli_ctx: CLI context instance.
        rich_output: Optional RichOutput presenter.

    Returns:
        CatalogDeleteCommandOutcome indicating deletion status.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not force:
        try:
            confirmed = typer.confirm(
                f"Are you sure you want to delete catalog blueprint '{sha_or_name}'?",
                default=False,
            )
        except typer.Abort:
            confirmed = False
        if not confirmed:
            output.info("Deletion cancelled.")
            return CatalogDeleteCommandOutcome(item=None, deleted=False, errors=["Deletion cancelled."])

    deleted_item = delete_catalog_item_by_sha_or_name(sha_or_name, cwd=cli_ctx.cwd, db=cli_ctx.db)
    if deleted_item is None:
        error_message = f"Catalog blueprint '{sha_or_name}' not found."
        output.error_panel("Catalog Delete Failed", error_message)
        return CatalogDeleteCommandOutcome(item=None, deleted=False, errors=[error_message])

    render_catalog_delete_success(deleted_item, rich_output=output)
    return CatalogDeleteCommandOutcome(item=deleted_item, deleted=True)
