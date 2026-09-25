"""Orchestration logic for ``wt blueprint create`` CLI command."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogCreateResult, CatalogItemType


def blueprint_create_command(
    context: CliContext,
    name: str,
    output_format: str = "terminal",
) -> CatalogCreateResult:
    """Create a new repo-tier blueprint file and reindex.

    Args:
        context: CLI context instance.
        name: Blueprint name.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        CatalogCreateResult containing created record or errors.
    """
    result = Catalog(path=context.cwd).create(item_type=CatalogItemType.BLUEPRINT, name=name)
    ui_dispatcher.dispatch(result, output_format=output_format)
    return result
