"""Orchestration logic for ``wt task`` CLI commands."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from pathlib import Path

import yaml

from getworktree.common.utils import RichOutput
from getworktree.core.catalog.inventory import (
    get_catalog_dir,
    get_catalog_item,
    scan_and_index_catalog,
)
from getworktree.core.db import (
    CatalogItemType,
    RunStatus,
    TaskRunRecord,
    TasksDb,
)
from getworktree.core.git_sandbox import GitSandboxManager, SandboxSession
from getworktree.core.step import (
    FailureAction,
    StepDefinition,
    StepType,
    execute_step,
)

from .models import (
    TaskBlueprintItem,
    TaskListCommandOutcome,
    TaskRunCommandOutcome,
    TaskShowCommandOutcome,
)
from .renderers import (
    render_task_list,
    render_task_run_success,
    render_task_show,
)

_DEFAULT_RICH_OUTPUT = RichOutput()
logger = logging.getLogger(__name__)


def task_list_command(
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TaskListCommandOutcome:
    """List task blueprints discovered under ``.worktree/catalog/tasks/`` and recorded task runs.

    Args:
        cwd: Optional working directory.
        rich_output: Optional RichOutput presenter.

    Returns:
        TaskListCommandOutcome containing listed task blueprint items, task run history, and errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT
    warnings: list[str] = []

    scan_res = scan_and_index_catalog(cwd=cwd)
    if not scan_res.ok:
        for err in scan_res.errors:
            output.error_panel("Task Catalog Scan Warning", err)

    task_records = [r for r in scan_res.items if r.item_type == CatalogItemType.TASK]
    catalog_dir = get_catalog_dir(cwd)

    items: list[TaskBlueprintItem] = []
    for record in task_records:
        file_path = catalog_dir / record.path
        use_git_worktree = True
        description = ""
        summary = ""
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                yaml_data = yaml.safe_load(content)
                if isinstance(yaml_data, dict):
                    description = str(yaml_data.get("description", ""))
                    summary = str(yaml_data.get("summary", ""))
                    if "use_git_worktree" in yaml_data:
                        use_git_worktree = bool(yaml_data.get("use_git_worktree", True))
            except Exception:
                pass

        items.append(
            TaskBlueprintItem(
                name=record.name,
                description=description,
                summary=summary,
                sha=record.sha,
                path=str(record.path),
                use_git_worktree=use_git_worktree,
            )
        )

    runs: list[TaskRunRecord] = []
    try:
        runs = TasksDb(cwd).list()
    except Exception as exc:
        warnings.append(f"Failed to query task run history from database: {exc}")
        logger.warning("Failed to query task run history from database: %s", exc)

    render_task_list(items, runs=runs, rich_output=output)

    return TaskListCommandOutcome(
        items=items,
        runs=runs,
        errors=list(scan_res.errors),
        warnings=warnings,
    )


def task_show_command(
    name: str,
    cwd: Path | None = None,
    *,
    rich_output: RichOutput | None = None,
) -> TaskShowCommandOutcome:
    """Show details and definition of a specific task blueprint.

    Args:
        name: Task name or SHA identifier.
        cwd: Optional working directory.
        rich_output: Optional RichOutput presenter.

    Returns:
        TaskShowCommandOutcome containing catalog item record and YAML definition.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    item = get_catalog_item(name, cwd=cwd)
    if item is None or item.item_type != CatalogItemType.TASK:
        error_msg = f"Task blueprint '{name}' not found."
        output.error_panel("Task Show Failed", error_msg)
        return TaskShowCommandOutcome(item=None, content=None, errors=[error_msg])

    catalog_dir = get_catalog_dir(cwd)
    file_path = catalog_dir / item.path

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        error_msg = f"Failed to read file for task blueprint '{name}': {exc}"
        output.error_panel("Task Show Failed", error_msg)
        return TaskShowCommandOutcome(item=item, content=None, errors=[error_msg])

    render_task_show(item, content, rich_output=output)
    return TaskShowCommandOutcome(item=item, content=content)


def task_run_command(
    name: str,
    cwd: Path | None = None,
    *,
    no_sandbox: bool = False,
    keep: bool = False,
    agent: str | None = None,
    session_id: str | None = None,
    execute_task_fn: Callable[[], None] | None = None,
    rich_output: RichOutput | None = None,
) -> TaskRunCommandOutcome:
    """Execute a task blueprint by name, running defined steps and persisting status.

    Args:
        name: Name of the task to run.
        cwd: Optional working directory.
        no_sandbox: When True, run execution in-place without creating a Git sandbox.
        keep: When True, retain the sandbox worktree after task completion.
        agent: Optional agent adapter override.
        session_id: Optional fixed session ID.
        execute_task_fn: Optional custom execution hook (for testing/simulation).
        rich_output: Optional RichOutput presenter.

    Returns:
        TaskRunCommandOutcome containing task run record, warnings, or errors.
    """
    output = rich_output or _DEFAULT_RICH_OUTPUT

    item = get_catalog_item(name, cwd=cwd)
    if item is None or item.item_type != CatalogItemType.TASK:
        error_msg = f"Task blueprint '{name}' not found."
        output.error_panel("Task Run Failed", error_msg)
        return TaskRunCommandOutcome(run_record=None, errors=[error_msg])

    catalog_dir = get_catalog_dir(cwd)
    file_path = catalog_dir / item.path

    task_use_git_wt = True
    yaml_data: dict = {}
    if file_path.exists():
        try:
            content = file_path.read_text(encoding="utf-8")
            parsed = yaml.safe_load(content)
            if isinstance(parsed, dict):
                yaml_data = parsed
                if "use_git_worktree" in yaml_data:
                    task_use_git_wt = bool(yaml_data.get("use_git_worktree", True))
        except Exception as exc:
            logger.warning("Failed to parse task blueprint YAML: %s", exc)

    effective_use_git_worktree = False if no_sandbox else task_use_git_wt
    root = (cwd or Path.cwd()).resolve()

    sid = session_id or f"task_{uuid.uuid4().hex[:8]}"
    warnings: list[str] = []
    run_record: TaskRunRecord | None = None

    try:
        run_record = TasksDb(cwd).insert(
            session_id=sid,
            task_name=name,
            status=RunStatus.RUNNING,
        )
    except Exception as exc:
        warnings.append(f"Failed to record task run start in database: {exc}")
        logger.warning("Failed to record task run start in database: %s", exc)

    run_status = RunStatus.RUNNING
    error_msg: str | None = None
    manager: GitSandboxManager | None = None
    session: SandboxSession | None = None

    try:
        output.info(f"Running task '{name}'...")
        if execute_task_fn is not None:
            execute_task_fn()
            run_status = RunStatus.COMPLETED
        else:
            # 1. Setup Sandbox or workspace root
            if effective_use_git_worktree:
                manager = GitSandboxManager(cwd=root)
                create_res = manager.create_sandbox_result(session_id=sid)
                if not create_res.ok or create_res.session is None:
                    err_detail = create_res.errors[0] if create_res.errors else "Sandbox creation failed."
                    raise RuntimeError(f"Git sandbox creation failed: {err_detail}")
                session = create_res.session
                sandbox_path = session.sandbox_path
                output.info(f"Sandbox: Active ({sandbox_path})")
            else:
                sandbox_path = root
                output.info("Sandbox: In-place (workspace)")

            # 2. Parse Step Definitions from task blueprint YAML
            raw_steps = yaml_data.get("steps") or yaml_data.get("commands") or []
            step_defs: list[StepDefinition] = []
            for idx, s in enumerate(raw_steps, start=1):
                if isinstance(s, dict):
                    step_id = str(s.get("id") or s.get("name") or f"step_{idx}")
                    step_name = str(s.get("name") or step_id)
                    st_str = str(s.get("type", "command")).lower()
                    try:
                        st = StepType(st_str)
                    except ValueError:
                        st = StepType.COMMAND

                    fa_str = str(s.get("failure_action", "abort")).lower()
                    try:
                        fa = FailureAction(fa_str)
                    except ValueError:
                        fa = FailureAction.ABORT

                    tools_list = s.get("tools") if isinstance(s.get("tools"), list) else []

                    step_def = StepDefinition(
                        id=step_id,
                        name=step_name,
                        type=st,
                        description=str(s.get("description", step_name)),
                        command=s.get("command"),
                        prompt=s.get("prompt"),
                        agent=agent or s.get("agent"),
                        tools=tools_list,
                        script_path=s.get("script_path"),
                        timeout_seconds=int(s.get("timeout_seconds", 120)),
                        failure_action=fa,
                    )
                    step_defs.append(step_def)

            if not step_defs:
                output.info("No step definitions found in task blueprint.")

            # 3. Execute Step Definitions
            total_steps = len(step_defs)
            for idx, step_def in enumerate(step_defs, start=1):
                cmd_info = f" (command: {step_def.command})" if step_def.command else ""
                output.info(f"[STEP {idx}/{total_steps}] Executing {step_def.name}{cmd_info}...")

                step_res = execute_step(
                    step=step_def,
                    sandbox_path=sandbox_path,
                    context={"agent": agent} if agent else None,
                )

                if step_res.ok:
                    output.info(f"[bold green][STEP {idx}/{total_steps}] {step_def.name} COMPLETED[/]")
                else:
                    output.info(
                        f"[bold red][STEP {idx}/{total_steps}] {step_def.name} FAILED[/]: {step_res.error_message or step_res.stderr}"
                    )
                    if step_def.failure_action == FailureAction.ABORT:
                        raise RuntimeError(
                            f"Step '{step_def.name}' failed: {step_res.error_message or step_res.stderr or 'exit code ' + str(step_res.exit_code)}"
                        )

            run_status = RunStatus.COMPLETED

    except KeyboardInterrupt:
        run_status = RunStatus.CANCELLED
        error_msg = "Task execution cancelled by user."
    except Exception as exc:
        run_status = RunStatus.FAILED
        error_msg = str(exc)

    # 4. Sandbox Cleanup (unless keep=True or sandbox not created)
    if manager is not None and session is not None:
        if not keep:
            try:
                manager.cleanup_sandbox(session)
                output.info("Sandbox: Cleaned")
            except Exception as exc:
                warnings.append(f"Failed to clean up sandbox: {exc}")
        else:
            output.info(f"Sandbox: Retained ({session.sandbox_path})")

    # 5. DB Status Update
    updated_record: TaskRunRecord | None = None
    try:
        updated_record = TasksDb(cwd).update_status(
            session_id=sid,
            status=run_status,
            error_message=error_msg,
        )
    except Exception as exc:
        warnings.append(f"Failed to update task run status in database: {exc}")
        logger.warning("Failed to update task run status in database: %s", exc)

    final_record = (
        updated_record
        or run_record
        or TaskRunRecord(
            id=-1,
            session_id=sid,
            task_name=name,
            status=run_status,
            started_at="",
            completed_at=None,
            error_message=error_msg,
        )
    )

    if run_status == RunStatus.COMPLETED:
        render_task_run_success(final_record, rich_output=output)
        return TaskRunCommandOutcome(run_record=final_record, warnings=warnings)
    elif run_status == RunStatus.CANCELLED:
        output.error_panel("Task Run Cancelled", error_msg or "Cancelled by user.")
        return TaskRunCommandOutcome(
            run_record=final_record,
            errors=[error_msg or "Task execution cancelled."],
            warnings=warnings,
        )
    else:
        output.error_panel("Task Run Failed", error_msg or "Task execution failed.")
        return TaskRunCommandOutcome(
            run_record=final_record,
            errors=[error_msg or "Task execution failed."],
            warnings=warnings,
        )
