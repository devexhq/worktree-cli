"""Pure text formatters for task resolve and run error panel bodies."""

from __future__ import annotations

from getworktree.common.models import DefinitionResolutionResult
from getworktree.core.db.models import CatalogRecord
from getworktree.core.runtime import RunOutcome


def format_task_resolve_failure(result: DefinitionResolutionResult[CatalogRecord]) -> str:
    """Return plain failure body text for a task resolution failure."""
    if result.errors:
        return "\n\n".join(result.errors)
    return "Failed to resolve task."


def format_task_run_failure(outcome: RunOutcome) -> str:
    """Return plain failure body text for a task execution failure."""
    if outcome.error_message:
        return outcome.error_message

    failed_messages = [result.error_message for result in outcome.step_results if result.error_message]
    if failed_messages:
        return "\n".join(failed_messages)

    return "Task execution failed."
