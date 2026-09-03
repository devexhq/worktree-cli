"""Root command execution logic for ``wt run``."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.run.formatters import register_run_formatters
from worktree.cli.run.models import BlueprintRunOutcome
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.engine import BlueprintRunService

register_run_formatters()


def run_command(
    context: CliContext,
    name: str,
    *,
    no_sandbox: bool = False,
    keep: bool = False,
    agent: str | None = None,
    session_id: str | None = None,
    non_interactive: bool = False,
    auto_apply: bool = False,
    cli_args: list[str] | None = None,
    output_format: str = "terminal",
) -> BlueprintRunOutcome:
    """Execute a task or workflow blueprint."""
    result = BlueprintRunService(
        name=name,
        path=context.cwd,
        runs_db=context.db.runs,
        catalog_db=context.db.catalog,
        kind=None,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        cli_args=cli_args,
        non_interactive=non_interactive,
        auto_apply=auto_apply,
    ).execute()
    ui_dispatcher.dispatch(result, output_format=output_format)
    return BlueprintRunOutcome(
        result=result,
        run_record=result.run_record,
        errors=result.errors,
        warnings=result.warnings,
    )
