"""Pure text formatters for task resolve and run error panel bodies."""

from __future__ import annotations

from worktree.common.models import DefinitionResolutionResult
from worktree.core.blueprint import BlueprintKind, BlueprintRenderer
from worktree.core.db.models import CatalogRecord
from worktree.core.runtime import RunOutcome

_TASK_RENDERER = BlueprintRenderer(BlueprintKind.TASK)


def format_task_resolve_failure(result: DefinitionResolutionResult[CatalogRecord]) -> str:
    """Return plain failure body text for a task resolution failure."""
    return _TASK_RENDERER.render_resolve_failure(result.errors)


def format_task_run_failure(outcome: RunOutcome) -> str:
    """Return plain failure body text for a task execution failure."""
    return _TASK_RENDERER.render(outcome)
