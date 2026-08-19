"""Workflow command handlers: list, show, run, and resume workflow sessions."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.cli.blueprint import BlueprintRunService
from worktree.cli.task.prompter import CliFailurePrompter
from worktree.common.utils import RichOutput
from worktree.core.blueprint import BlueprintKind, BlueprintRunCommandOutcome
from worktree.core.config.loader import load_config_result
from worktree.core.db import RunStatus, SandboxesDb, WorkflowsDb
from worktree.core.engine import Engine, EngineResumeError, EngineRuntimeError

from .renderers import render_workflow_list

rich_output = RichOutput()


def workflow_list_command(*, cwd: Path | None = None) -> None:
    """Query recorded workflow run sessions and render a formatted table.

    Read-only: does not mutate workflow files or start sandboxes.
    Exit ``0`` on success (including when no recorded workflows exist);
    exit ``1`` on uninitialized worktree or config load failure.

    Args:
        cwd: Repository root. Defaults to process CWD.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok or load.config is None:
        message = load.errors[0] if load.errors else "Worktree is not initialized. Run `wt init`."
        rich_output.error_panel("Workflow List Failed", message)
        raise typer.Exit(code=1)

    workflows = WorkflowsDb(root).list()
    render_workflow_list(workflows, cwd=root, rich_output=rich_output)
    raise typer.Exit(code=0)


def workflow_show_command(session_id: str, *, cwd: Path | None = None) -> None:
    """Show details for a specific workflow session by session ID.

    Read-only: does not mutate workflow files or start sandboxes.
    Exit ``0`` when workflow session is found; exit ``1`` on failure or missing session.

    Args:
        session_id: Workflow session ID to show.
        cwd: Repository root. Defaults to process CWD.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok or load.config is None:
        message = load.errors[0] if load.errors else "Worktree is not initialized. Run `wt init`."
        rich_output.error_panel("Workflow Show Failed", message)
        raise typer.Exit(code=1)

    row = WorkflowsDb(root).get(session_id) or SandboxesDb(root).get(session_id)
    if row is None:
        rich_output.error_panel(
            "Workflow Show Failed",
            f"Workflow session '{session_id}' not found.",
        )
        raise typer.Exit(code=1)

    sid = getattr(row, "session_id", getattr(row, "id", session_id))
    name = getattr(row, "workflow_name", getattr(row, "name", None)) or "-"
    branch = getattr(row, "branch_name", "-")
    status = row.status.value if hasattr(row.status, "value") else str(row.status)
    started = getattr(row, "started_at", getattr(row, "created_at", "-"))
    completed = getattr(row, "completed_at", None)
    err_msg = getattr(row, "error_message", None)

    rich_output.info(f"Workflow Session: {sid}")
    rich_output.info(f"Name:             {name}")
    rich_output.info(f"Branch:           {branch}")
    rich_output.info(f"Status:           {status}")
    rich_output.info(f"Started At:       {started}")
    if completed:
        rich_output.info(f"Completed At:     {completed}")
    if err_msg:
        rich_output.info(f"Error:            {err_msg}")
    raise typer.Exit(code=0)


def workflow_resume_command(session_id: str, *, cwd: Path | None = None) -> None:
    """Resume a paused workflow session by session ID.

    Exit ``0`` when the session resumes successfully; exit ``1`` on classified
    resume errors (unknown id, wrong status, missing sandbox, corrupt checkpoint).

    Args:
        session_id: Workflow session ID to resume.
        cwd: Repository root. Defaults to process CWD.
    """
    root = (cwd or Path.cwd()).resolve()
    load = load_config_result(cwd=root)
    if not load.ok or load.config is None:
        message = load.errors[0] if load.errors else "Worktree is not initialized. Run `wt init`."
        rich_output.error_panel("Workflow Resume Failed", message)
        raise typer.Exit(code=1)

    if WorkflowsDb(root).get(session_id) is None:
        rich_output.error_panel(
            "Workflow Resume Failed",
            f"Workflow session '{session_id}' not found.",
        )
        raise typer.Exit(code=1)

    rich_output.info(f"Resuming workflow session '{session_id}'...")
    prompter = CliFailurePrompter(rich_output, kind="workflow")
    non_interactive = not prompter.is_interactive
    try:
        outcome = Engine(root).resume(
            session_id,
            failure_prompter=None if non_interactive else prompter,
            non_interactive=non_interactive,
        )
    except (EngineResumeError, EngineRuntimeError) as exc:
        rich_output.error_panel("Workflow Resume Failed", str(exc))
        raise typer.Exit(code=1) from None

    if outcome.ok or outcome.status == RunStatus.PAUSED:
        raise typer.Exit(code=0)

    message = outcome.error_message or f"Cannot resume session '{session_id}'."
    rich_output.error_panel("Workflow Resume Failed", message)
    raise typer.Exit(code=1)


def workflow_run_command(
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
    """Resolve and validate a workflow definition, then execute via Engine.

    Args:
        name: Workflow definition name.
        cwd: Repository root. Defaults to process CWD.
        no_sandbox: Run execution in-place without creating a sandbox.
        keep: Retain sandbox worktree after completion.
        agent: Override default target agent adapter.
        session_id: Explicit session identifier.
        cli_args: Trailing CLI tokens for declared workflow inputs.
        non_interactive: Disable interactive prompts; prompt_user failures abort.
        rich_output: Optional RichOutput instance for console rendering.
    """
    return BlueprintRunService(
        name=name,
        kind=BlueprintKind.WORKFLOW,
        cwd=cwd,
        no_sandbox=no_sandbox,
        keep=keep,
        agent=agent,
        session_id=session_id,
        cli_args=cli_args,
        non_interactive=non_interactive,
        output=rich_output or RichOutput(),
    ).execute()
