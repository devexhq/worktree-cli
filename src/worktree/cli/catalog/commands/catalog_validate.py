"""Orchestration logic for ``wt catalog validate`` CLI command."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.blueprint.models import BlueprintDefinition
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogValidateResult
from worktree.core.db import CatalogItemType
from worktree.core.step.models import StepDefinition


def catalog_validate_command(
    context: CliContext,
    target: str,
    item_type: CatalogItemType | None = None,
    output_format: str = "terminal",
) -> CatalogValidateResult:
    """Validate a catalog blueprint or step definition without executing it.

    Args:
        context: CLI context instance.
        target: Catalog item name, namespaced identifier, or file path to validate.
        item_type: Item type to validate a file-path target against; ignored for a catalog-name target.
        output_format: Presentation format ("terminal" or "json").

    Returns:
        CatalogValidateResult containing status, resolved path, errors, and warnings.
    """
    result = Catalog(path=context.cwd, db=context.db.catalog).validate(
        target,
        item_type=item_type,
        blueprint_cls=BlueprintDefinition,
        step_cls=StepDefinition,
    )
    ui_dispatcher.dispatch(result, output_format=output_format)
    return result
