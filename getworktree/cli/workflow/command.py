"""Workflow command handlers: list, show, run, and resume workflow sessions."""

from __future__ import annotations

from pathlib import Path

import typer

from getworktree.common.utils import RichOutput
from getworktree.core.config.loader import ConfigLoadStatus, load_config_result
from getworktree.core.db import SandboxesDb, WorkflowsDb
from getworktree.core.workflows.render import (
    format_workflow_show_resolve_failure,
    format_workflow_show_validate_failure,
)
from getworktree.core.workflows.resolve import resolve_workflow_by_name
from getworktree.core.workflows.validate import validate_workflow_result

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
    """Resume an interrupted workflow session by session ID.

    Exit ``0`` when workflow session is resumed; exit ``1`` on missing session.

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

    row = WorkflowsDb(root).get(session_id) or SandboxesDb(root).get(session_id)
    if row is None:
        rich_output.error_panel(
            "Workflow Resume Failed",
            f"Workflow session '{session_id}' not found.",
        )
        raise typer.Exit(code=1)

    rich_output.info(f"Resuming workflow session '{session_id}'...")
    raise typer.Exit(code=0)


def workflow_run_command(
    name: str,
    *,
    cwd: Path | None = None,
) -> None:
    """Resolve and validate a workflow definition, then report execution status.

    The Workflow Spec v1 execution engine (step assertion checks, failure
    policy, loop control-flow) has not landed yet; see
    getworktree/getworktree#171, #172, and #173. Until it does, this command
    validates the workflow definition and exits without executing any steps.

    Args:
        name: Workflow definition name.
        cwd: Repository root. Defaults to process CWD.
    """
    root = (cwd or Path.cwd()).resolve()

    load = load_config_result(cwd=root)
    if load.status == ConfigLoadStatus.NOT_FOUND:
        rich_output.error_panel(
            "Workflow Run Failed",
            load.errors[0] if load.errors else "Worktree is not initialized. Run `wt init`.",
        )
        raise typer.Exit(code=1)
    if not load.ok or load.config is None:
        detail = load.errors[0] if load.errors else "Invalid configuration."
        rich_output.error_panel("Workflow Run Failed", detail)
        raise typer.Exit(code=1)

    resolved = resolve_workflow_by_name(name, cwd=root)
    if not resolved.ok:
        rich_output.error_panel(
            "Workflow Run Failed",
            format_workflow_show_resolve_failure(resolved),
        )
        raise typer.Exit(code=1)

    assert resolved.entry is not None
    validated = validate_workflow_result(resolved.entry.source_path)
    if not validated.ok:
        rich_output.error_panel(
            "Workflow Run Failed",
            format_workflow_show_validate_failure(validated),
        )
        raise typer.Exit(code=1)

    rich_output.error_panel(
        "Workflow Run Not Implemented",
        f"'{name}' is a valid workflow definition, but step execution is not "
        "implemented yet.\n"
        "Tracked in getworktree/getworktree#171, #172, and #173.",
    )
    raise typer.Exit(code=1)
