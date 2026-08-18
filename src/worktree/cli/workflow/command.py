"""Workflow command handlers: list, show, run, and resume workflow sessions."""

from __future__ import annotations

from pathlib import Path

import typer

from worktree.cli.task.observer import resolve_run_observer
from worktree.cli.task.prompter import CliFailurePrompter
from worktree.common.utils import RichOutput
from worktree.core.blueprint import (
    Blueprint,
    BlueprintKind,
    BlueprintLoadError,
    BlueprintNotFoundError,
    BlueprintRenderer,
    BlueprintValidationError,
)
from worktree.core.catalog import Catalog
from worktree.core.config.loader import ConfigLoadStatus, load_config_result
from worktree.core.db import RunStatus, SandboxesDb, WorkflowRunRecord, WorkflowsDb
from worktree.core.engine import Engine, EngineInputError, EngineResumeError, EngineRuntimeError, RunRequest
from worktree.core.inputs import format_input_error_message
from worktree.core.runtime import FailurePrompter, RunOutcome

from .renderers import render_workflow_list, render_workflow_run_success

rich_output = RichOutput()
_WORKFLOW_RENDERER = BlueprintRenderer(BlueprintKind.WORKFLOW)


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


def _load_workflow_blueprint(name: str, root: Path) -> Blueprint:
    """Load a workflow blueprint from catalog; exit on failure or kind mismatch."""
    catalog = Catalog(root)
    try:
        blueprint = Blueprint.load(name, catalog=catalog)
    except (BlueprintNotFoundError, BlueprintLoadError) as exc:
        rich_output.error_panel(
            "Workflow Run Failed",
            _WORKFLOW_RENDERER.render_resolve_failure([str(exc)]),
        )
        raise typer.Exit(code=1) from None
    except BlueprintValidationError as exc:
        rich_output.error_panel(
            "Workflow Run Failed",
            _WORKFLOW_RENDERER.render_validate_failure([str(exc)]),
        )
        raise typer.Exit(code=1) from None

    if blueprint.kind is not BlueprintKind.WORKFLOW:
        rich_output.error_panel(
            "Workflow Run Failed",
            f"Blueprint '{name}' is a {blueprint.kind.value}; wt workflow run requires a workflow.",
        )
        raise typer.Exit(code=1)

    return blueprint


def _resolve_failure_prompter(
    output: RichOutput,
    *,
    non_interactive: bool,
) -> tuple[bool, FailurePrompter | None]:
    """Build the CLI prompter and effective non-interactive flag (TTY-aware)."""
    if non_interactive:
        return True, None
    prompter = CliFailurePrompter(output, kind="workflow")
    if not prompter.is_interactive:
        return True, None
    return False, prompter


def _load_run_record(cwd: Path, session_id: str) -> WorkflowRunRecord | None:
    """Return the persisted workflow row, or None when lookup fails."""
    try:
        return WorkflowsDb(cwd).get(session_id)
    except Exception:
        return None


def _fallback_run_record(
    session_id: str,
    workflow_name: str,
    status: RunStatus,
    error_message: str | None,
) -> WorkflowRunRecord:
    return WorkflowRunRecord(
        id=-1,
        session_id=session_id,
        workflow_name=workflow_name,
        branch_name="",
        status=status,
        started_at="",
        completed_at=None,
        error_message=error_message,
    )


def _finalize_run_outcome(
    *,
    name: str,
    session_id: str,
    run_outcome: RunOutcome,
    run_record: WorkflowRunRecord | None,
    output: RichOutput,
) -> None:
    """Render run result and exit with appropriate exit code."""
    final_record = run_record or _fallback_run_record(
        session_id,
        name,
        run_outcome.status,
        run_outcome.error_message,
    )

    if run_outcome.ok:
        render_workflow_run_success(final_record, rich_output=output)
        raise typer.Exit(code=0)

    if run_outcome.status == RunStatus.PAUSED:
        message = run_outcome.error_message or "Workflow paused; checkpoint saved."
        output.info(message)
        raise typer.Exit(code=0)

    if run_outcome.status == RunStatus.CANCELLED:
        message = run_outcome.error_message or "Cancelled by user."
        output.error_panel("Workflow Run Cancelled", message)
        raise typer.Exit(code=1)

    message = _WORKFLOW_RENDERER.render(run_outcome)
    output.error_panel("Workflow Run Failed", message)
    raise typer.Exit(code=1)


def workflow_run_command(
    name: str,
    *,
    cwd: Path | None = None,
    no_sandbox: bool = False,
    keep: bool = False,
    agent: str | None = None,
    session_id: str | None = None,
    cli_args: list[str] | None = None,
    non_interactive: bool = False,
) -> None:
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
    """
    root = (cwd or Path.cwd()).resolve()
    _require_workflow_config(root)

    blueprint = _load_workflow_blueprint(name, root)

    effective_non_interactive, failure_prompter = _resolve_failure_prompter(
        rich_output,
        non_interactive=non_interactive,
    )
    rich_output.info(f"Running workflow '{name}'...")
    observer = resolve_run_observer(rich_output, non_interactive=effective_non_interactive)

    try:
        with observer:
            run_outcome = Engine(root).run(
                blueprint,
                RunRequest(
                    cli_args=cli_args,
                    use_sandbox=not no_sandbox,
                    keep=keep,
                    agent=agent,
                    session_id=session_id,
                    observer=observer,
                    failure_prompter=failure_prompter,
                    non_interactive=effective_non_interactive,
                ),
            )
    except EngineInputError as exc:
        rich_output.error_panel(
            "Workflow Run Failed",
            format_input_error_message(
                kind="workflow",
                name=name,
                result=exc.result,
                declarations=blueprint.inputs,
            ),
        )
        raise typer.Exit(code=1) from None
    except EngineRuntimeError as exc:
        rich_output.error_panel("Workflow Run Failed", str(exc))
        raise typer.Exit(code=1) from None

    sid = run_outcome.session_id or ""
    for warning in run_outcome.warnings:
        rich_output.info(warning)

    _finalize_run_outcome(
        name=name,
        session_id=sid,
        run_outcome=run_outcome,
        run_record=_load_run_record(root, sid) if sid else None,
        output=rich_output,
    )
