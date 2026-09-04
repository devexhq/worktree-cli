"""ComponentFormatter for SandboxShowResult."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.formatters.common import build_error_panel
from worktree.cli.ui.formatters.sandbox.common import build_sandbox_detail_table
from worktree.common.types import ComponentFormatter
from worktree.core.sandbox.models import SandboxShowResult, SandboxShowStatus


def _format_show_error_panel(data: SandboxShowResult) -> Panel:
    """Format error panel for non-ok sandbox show results."""
    if data.status == SandboxShowStatus.NOT_INITIALIZED:
        fixes = data.fixes or ["Run `wt init` to create `.worktree/config.json`"]
        return build_error_panel(
            "Worktree Not Initialized",
            data.errors,
            "Worktree workspace is not initialized.",
            fixes,
        )

    if data.status == SandboxShowStatus.NOT_FOUND:
        fixes = data.fixes or ["Run `wt sandbox list` to see known sandboxes"]
        return build_error_panel(
            "Sandbox Not Found",
            data.errors,
            "Sandbox not found.",
            fixes,
        )

    return build_error_panel(
        "Sandbox Show Failed",
        data.errors,
        "Failed to show sandbox.",
        data.fixes,
    )


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
