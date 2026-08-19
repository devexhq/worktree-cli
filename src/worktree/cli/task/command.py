"""Orchestration logic for ``wt task`` CLI commands."""

from __future__ import annotations

import logging
from pathlib import Path

from worktree.cli.blueprint import BlueprintRunService
from worktree.common.utils import RichOutput
from worktree.core.blueprint import BlueprintKind, BlueprintRunCommandOutcome
from worktree.core.db import TaskRunRecord, TasksDb

from .models import TaskListCommandOutcome
from .renderers import render_task_list

_DEFAULT_RICH_OUTPUT = RichOutput()
logger = logging.getLogger(__name__)


def task_list_command(
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TaskListCommandOutcome:
    """List recorded task runs. Blueprint inventory lives under ``wt catalog``."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    warnings: list[str] = []
    errors: list[str] = []

    runs: list[TaskRunRecord] = []
    try:
        runs = TasksDb(cwd).list()
    except Exception as exc:
        warnings.append(f"Failed to query task run history from database: {exc}")
        logger.warning("Failed to query task run history from database: %s", exc)

    render_task_list(runs=runs, rich_output=output)
    return TaskListCommandOutcome(
        runs=runs,
        errors=errors,
        warnings=warnings,
    )


def task_run_command(
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
    """Resolve a task blueprint, execute it via Engine, and return the CLI outcome."""
    return BlueprintRunService(
        name=name,
        kind=BlueprintKind.TASK,
        cwd=cwd,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        cli_args=cli_args,
        non_interactive=non_interactive,
        output=rich_output or _DEFAULT_RICH_OUTPUT,
    ).execute()
