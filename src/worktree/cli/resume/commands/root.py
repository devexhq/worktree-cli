"""Root command execution logic for ``wt resume``."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.resume.models import BlueprintResumeOutcome
from worktree.cli.run.formatters import register_run_formatters
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.engine import BlueprintResumeService

register_run_formatters()


def resume_command(
    context: CliContext,
    session_id: str | None = None,
    *,
    non_interactive: bool = False,
    output_format: str = "terminal",
) -> BlueprintResumeOutcome:
    """Resume a paused task or workflow blueprint execution session."""
    result = BlueprintResumeService(
        path=context.cwd,
        db=context.db.runs,
        catalog_db=context.db.catalog,
        session_id=session_id,
        non_interactive=non_interactive,
    ).execute()
    ui_dispatcher.dispatch(result, output_format=output_format)
    return BlueprintResumeOutcome(
        result=result,
        run_record=result.run_record,
        errors=result.errors,
        warnings=result.warnings,
    )
