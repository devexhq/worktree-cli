"""Root command execution logic for ``wt resume``."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.blueprint import BlueprintRunCommandOutcome
from worktree.core.engine import BlueprintResumeService


def resume_command(
    context: CliContext,
    session_id: str | None = None,
    *,
    non_interactive: bool = False,
) -> BlueprintRunCommandOutcome:
    """Resume a paused task or workflow blueprint execution session."""
    return BlueprintResumeService(
        path=context.cwd,
        db=context.db.runs,
        catalog_db=context.db.catalog,
        output=context.output,
        session_id=session_id,
        non_interactive=non_interactive,
        config=context.config,
    ).execute()
