"""ComponentFormatter for SandboxShowResult."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.formatters.sandbox.common import build_sandbox_detail_table
from worktree.common.types import ComponentFormatter
from worktree.core.sandbox.models import SandboxShowResult, SandboxShowStatus


def _format_show_error_panel(data: SandboxShowResult) -> Panel:
    """Format error panel for non-ok sandbox show results."""
    if data.status == SandboxShowStatus.NOT_INITIALIZED:
        err_msg = "\n\n".join(data.errors) if data.errors else "Worktree workspace is not initialized."
        fixes = data.fixes or ["Run `wt init` to create `.worktree/config.json`"]
        return Panel(
            f"{err_msg}\nFix:\n" + "\n".join(f"- {fix}" for fix in fixes),
            title="Worktree Not Initialized",
            border_style="red",
        )

    if data.status == SandboxShowStatus.NOT_FOUND:
        msg = data.errors[0] if data.errors else "Sandbox not found."
        fixes = data.fixes or ["Run `wt sandbox list` to see known sandboxes"]
        return Panel(
            f"{msg}\nFix:\n" + "\n".join(f"- {fix}" for fix in fixes),
            title="Sandbox Not Found",
            border_style="red",
        )

    err_msg = "\n\n".join(data.errors) if data.errors else "Failed to show sandbox."
    if data.fixes:
        err_msg += "\nFix:\n" + "\n".join(f"- {fix}" for fix in data.fixes)
    return Panel(err_msg, title="Sandbox Show Failed", border_style="red")


class SandboxShowFormatter(ComponentFormatter[SandboxShowResult]):
    """Formatter for sandbox show command results."""

    def to_rich(self, data: SandboxShowResult) -> Any:
        """Render key-value detail table or error status."""
        if data.ok and data.sandbox is not None:
            table = build_sandbox_detail_table(data.sandbox, disk_present=data.disk_present)
            if data.reconciled:
                return Group(
                    table,
                    Text("Note: sandbox directory is missing; status updated to 'cleaned'.", style="dim"),
                )
            return table

        return _format_show_error_panel(data)

    def to_json_serializable(self, data: SandboxShowResult) -> dict[str, Any]:
        """Convert SandboxShowResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
