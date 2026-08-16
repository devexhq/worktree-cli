"""Rich-facing formatters for ``wt workflow`` list output."""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from getworktree.common.utils import RichOutput, enum_value
from getworktree.core.db import SandboxRecord, WorkflowRunRecord
from getworktree.core.inputs import ParameterInput

_DEFAULT_RICH_OUTPUT = RichOutput()


def build_recorded_workflows_table(
    workflows: list[WorkflowRunRecord] | list[SandboxRecord],
    *,
    cwd: Path | None = None,
) -> Table:
    """Build the ``Recorded Workflows`` table for workflow list output.

    Args:
        workflows: List of recorded workflow run or sandbox session rows from database.
        cwd: Repository root for relative path display.

    Returns:
        A Rich table with SESSION ID, WORKFLOW NAME, BRANCH, STATUS, STARTED AT columns.
    """
    table = Table(title="Recorded Workflows", title_justify="left", show_header=True)
    table.add_column("SESSION ID", style="cyan", no_wrap=True)
    table.add_column("WORKFLOW NAME", no_wrap=True)
    table.add_column("BRANCH", no_wrap=True)
    table.add_column("STATUS")
    table.add_column("STARTED AT", no_wrap=True)

    for row in workflows:
        sid = getattr(row, "session_id", getattr(row, "id", "-"))
        name = getattr(row, "workflow_name", getattr(row, "name", "-")) or "-"
        branch = getattr(row, "branch_name", "-")
        status = enum_value(row.status)
        started = getattr(row, "started_at", getattr(row, "created_at", "-"))
        table.add_row(
            sid,
            name,
            branch,
            status,
            started,
        )
    return table


def render_workflow_list(
    workflows: list[WorkflowRunRecord] | list[SandboxRecord],
    *,
    cwd: Path | None = None,
    rich_output: RichOutput | None = None,
) -> None:
    """Render empty state or the recorded workflows table."""
    output = rich_output or _DEFAULT_RICH_OUTPUT

    if not workflows:
        output.info("No recorded workflows found.")
    else:
        output.info(build_recorded_workflows_table(workflows, cwd=cwd))


def render_workflow_inputs(
    inputs: dict[str, ParameterInput],
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render declared workflow input parameters."""
    output = rich_output or _DEFAULT_RICH_OUTPUT
    if not inputs:
        return

    output.info("[bold cyan]Inputs:[/]")
    for name, spec in inputs.items():
        required = "required" if spec.required else "optional"
        default = f", default={spec.default!r}" if spec.default is not None else ""
        aliases = f", aliases={spec.aliases}" if spec.aliases else ""
        description = f" — {spec.description}" if spec.description else ""
        output.info(f"  - {name} ({enum_value(spec.type)}, {required}{default}{aliases}){description}")
