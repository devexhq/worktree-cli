"""Root command execution logic for ``wt run``."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.run.observer import resolve_cli_observer
from worktree.cli.ui import (
    ErrorPanelEvent,
    MessageEvent,
    RunSuccessEvent,
    WarningEvent,
    ui_dispatcher,
)
from worktree.common.utils import RichOutput
from worktree.core.blueprint.models import BlueprintKind, BlueprintRunResult
from worktree.core.catalog import Catalog
from worktree.core.db import RunRecord, RunStatus
from worktree.core.engine import BlueprintRunService
from worktree.core.runtime import CliFailurePrompter


def _resolve_blueprint_label(context: CliContext, name: str) -> tuple[str, BlueprintKind]:
    catalog = Catalog(context.cwd, db=context.db.catalog)
    res = catalog.get(name)
    if res.ok and res.resolved is not None and res.resolved.item_type.value in ("task", "workflow"):
        kind_label = res.resolved.item_type.value
        kind_val = BlueprintKind.WORKFLOW if kind_label == "workflow" else BlueprintKind.TASK
        return kind_label, kind_val
    return "task", BlueprintKind.TASK


def _first_error(result: BlueprintRunResult, fallback: str) -> str:
    return result.errors[0] if result.errors else fallback


def _dispatch_run_outcome(
    result: BlueprintRunResult,
    record: RunRecord | None,
    kind_title: str,
) -> None:
    """Dispatch the appropriate UI event for a completed blueprint run."""
    if result.ok and record is not None:
        ui_dispatcher.dispatch(
            RunSuccessEvent(
                session_id=record.session_id,
                blueprint_name=record.blueprint_name,
                kind=record.kind or BlueprintKind.TASK,
                status=record.status,
            )
        )
    elif record is not None and record.status == RunStatus.PAUSED:
        ui_dispatcher.dispatch(MessageEvent(message=_first_error(result, f"{kind_title} paused; checkpoint saved.")))
    elif record is not None and record.status == RunStatus.CANCELLED:
        ui_dispatcher.dispatch(
            ErrorPanelEvent(
                title=f"{kind_title} Run Cancelled",
                message=_first_error(result, "Cancelled by user."),
            )
        )
    else:
        msg = "\n\n".join(result.errors) if result.errors else f"{kind_title} execution failed."
        ui_dispatcher.dispatch(ErrorPanelEvent(title=f"{kind_title} Run Failed", message=msg))


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
) -> BlueprintRunResult:
    """Execute a task or workflow blueprint."""
    ui_dispatcher.set_output_format(output_format)
    kind_label, default_kind = _resolve_blueprint_label(context, name)
    ui_dispatcher.dispatch(MessageEvent(message=f"Running {kind_label} '{name}'..."))

    observer = resolve_cli_observer(
        ui_dispatcher,
        non_interactive=non_interactive,
        output_format=output_format,
    )
    with observer:
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
            observer=observer,
            failure_prompter=CliFailurePrompter(RichOutput(ui_dispatcher._console)),
        ).execute()

    for warning in result.warnings:
        ui_dispatcher.dispatch(WarningEvent(message=warning))

    record = result.run_record
    effective_kind = record.kind if record is not None and record.kind is not None else default_kind
    kind_title = effective_kind.value.capitalize()
    _dispatch_run_outcome(result, record, kind_title)
    return result
