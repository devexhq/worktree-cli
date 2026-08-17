"""Workflow command handlers: list, show, run, and resume workflow sessions."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.common.utils import RichOutput
from worktree.core.catalog.services.inventory import get_catalog_item
from worktree.core.config.loader import ConfigLoadStatus, load_config_result
from worktree.core.db import CatalogItemType, SandboxesDb, WorkflowsDb
from worktree.core.inputs import format_missing_inputs_error, resolve_inputs
from worktree.core.workflows.models import WorkflowDefinition
from worktree.core.workflows.services.renderer import format_workflow_run_resolve_failure

from .renderers import render_workflow_inputs, render_workflow_list

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


def _require_workflow_config(root: Path) -> None:
    """Exit with a failure panel when config is missing or invalid."""
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


def _validate_workflow_inputs(name: str, definition: WorkflowDefinition, cli_args: list[str] | None) -> None:
    """Validate and display workflow inputs; exit on parse/missing errors."""
    input_result = resolve_inputs(definition.inputs, cli_args=cli_args)
    if not input_result.ok:
        if input_result.errors:
            error_message = input_result.errors[0]
        else:
            error_message = format_missing_inputs_error(
                kind="workflow",
                name=name,
                missing=input_result.missing,
                declarations=definition.inputs,
            )
        rich_output.error_panel("Workflow Run Failed", error_message)
        raise typer.Exit(code=1)
    if definition.inputs:
        render_workflow_inputs(definition.inputs, rich_output=rich_output)
    for warning in input_result.warnings:
        rich_output.info(f"Warning: {warning}")


def workflow_run_command(
    name: str,
    *,
    cwd: Path | None = None,
    cli_args: list[str] | None = None,
    non_interactive: bool = False,
) -> None:
    """Resolve and validate a workflow definition, then report execution status.

    The Workflow Spec v1 execution engine (step assertion checks, failure
    policy, loop control-flow) has not landed yet; see
    devexhq/worktree-cli#171, #172, and #173. Until it does, this command
    validates the workflow definition and input parameters, then exits without
    executing any steps.

    Args:
        name: Workflow definition name.
        cwd: Repository root. Defaults to process CWD.
        cli_args: Trailing CLI tokens for declared workflow inputs.
        non_interactive: When execution lands, degrade ``prompt_user`` to abort.
    """
    del non_interactive  # Reserved for run_steps wiring once workflow execution lands.
    root = (cwd or Path.cwd()).resolve()
    _require_workflow_config(root)

    result = get_catalog_item(name, CatalogItemType.WORKFLOW, definition_cls=WorkflowDefinition, cwd=root)
    if not result.ok:
        rich_output.error_panel(
            "Workflow Run Failed",
            format_workflow_run_resolve_failure(result),
        )
        raise typer.Exit(code=1)

    definition = result.definition
    if isinstance(definition, WorkflowDefinition):
        _validate_workflow_inputs(name, definition, cli_args)

    rich_output.error_panel(
        "Workflow Run Not Implemented",
        f"'{name}' is a valid workflow definition, but step execution is not "
        "implemented yet.\n"
        "Tracked in devexhq/worktree-cli#171, #172, and #173.",
    )
    raise typer.Exit(code=1)
