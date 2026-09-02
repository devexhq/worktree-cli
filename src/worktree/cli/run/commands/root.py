"""Root command execution logic for ``wt run``."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.core.blueprint import BlueprintRunCommandOutcome
from worktree.core.engine import BlueprintRunService


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
) -> BlueprintRunCommandOutcome:
    """Execute a task or workflow blueprint."""
    return BlueprintRunService(
        name=name,
        path=context.cwd,
        runs_db=context.db.runs,
        catalog_db=context.db.catalog,
        output=context.output,
        kind=None,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        cli_args=cli_args,
        non_interactive=non_interactive,
        auto_apply=auto_apply,
        config=context.config,
    ).execute()
