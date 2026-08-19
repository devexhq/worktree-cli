"""Root command execution logic for ``wt run``."""

from __future__ import annotations

from pathlib import Path

from worktree.cli.blueprint import BlueprintRunService
from worktree.common.utils import RichOutput
from worktree.core.blueprint import BlueprintRunCommandOutcome


def root_command(
    name: str,
    cwd: Path | None = None,
    *,
    no_sandbox: bool = False,
    keep: bool = False,
    agent: str | None = None,
    session_id: str | None = None,
    cli_args: list[str] | None = None,
    non_interactive: bool = False,
    rich_output: RichOutput | None = None,
) -> BlueprintRunCommandOutcome:
    """Execute a task or workflow blueprint by name via BlueprintRunService."""
    return BlueprintRunService(
        name=name,
        kind=None,
        cwd=cwd,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        cli_args=cli_args,
        non_interactive=non_interactive,
        output=rich_output or RichOutput(),
    ).execute()
