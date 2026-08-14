"""Resolve and load task blueprints from the catalog inventory."""

from __future__ import annotations

from pathlib import Path

from getworktree.common.models import DefinitionResolutionResult
from getworktree.core.catalog.services.inventory import get_catalog_item
from getworktree.core.db import CatalogItemType, CatalogRecord
from getworktree.core.task.models import TaskDefinition


def resolve_and_load_task(
    name: str,
    cwd: Path | None = None,
) -> DefinitionResolutionResult[CatalogRecord]:
    """Resolve a task blueprint by name from catalog inventory and validate its model.

    Args:
        name: Task blueprint name or SHA to resolve.
        cwd: Optional working directory used to locate ``.worktree/``.

    Returns:
        A ``DefinitionResolutionResult`` whose ``definition`` is a ``TaskDefinition``
        when status is ``OK``.
    """
    return get_catalog_item(
        name,
        CatalogItemType.TASK,
        definition_cls=TaskDefinition,
        cwd=cwd,
    )
