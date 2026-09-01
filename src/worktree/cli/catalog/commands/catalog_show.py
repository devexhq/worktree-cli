"""Orchestration logic for ``wt catalog show`` CLI command."""

from __future__ import annotations

from worktree.cli.catalog.models import CatalogShowCommandOutcome
from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog


def catalog_show_command(
    context: CliContext,
    sha_or_name: str,
    output_format: str = "terminal",
) -> CatalogShowCommandOutcome:
    """Show details and definition content of a catalog blueprint.

    Args:
        context: CLI context instance.
        sha_or_name: SHA identifier or name of the blueprint.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        CatalogShowCommandOutcome containing record and content or errors.
    """
    result = Catalog(path=context.cwd, db=context.db.catalog).show(sha_or_name)
    ui_dispatcher.dispatch(result, output_format=output_format)
    return CatalogShowCommandOutcome(
        result=result,
        item=result.item,
        content=result.content,
        errors=list(result.errors),
    )
