"""Handles local workspace initialization (`wt init`)."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.core.bootstrap import initialize_workspace

from ..models import InitCommandOutcome


def init_command(
    context: CliContext,
    tool_version: str | None = None,
    overwrite: bool = False,
    repair: bool = False,
    output_format: str = "terminal",
) -> InitCommandOutcome:
    """Initialize a local project workspace for Worktree CLI and desktop sync.

    Args:
        context: CLI context instance.
        tool_version: Optional version stamp for bootstrap metadata.
        overwrite: When True, replace existing config with V1 defaults.
        repair: When True, non-destructively add missing required keys.
        output_format: Presentation format ("terminal" or "json").
    """
    result = initialize_workspace(
        context.cwd,
        tool_version=tool_version,
        overwrite=overwrite,
        repair=repair,
    )
    ui_dispatcher.dispatch(result, output_format=output_format)
    return InitCommandOutcome(result=result, errors=list(result.errors))
