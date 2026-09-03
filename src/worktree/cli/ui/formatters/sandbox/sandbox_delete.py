"""ComponentFormatter for SandboxDeleteResult."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.text import Text

from worktree.common.types import ComponentFormatter
from worktree.core.sandbox.models import SandboxDeleteResult, SandboxDeleteStatus


def _format_delete_error_panel(data: SandboxDeleteResult) -> Panel:
    """Format error panel for non-ok sandbox delete results."""
    if data.status == SandboxDeleteStatus.NOT_INITIALIZED:
        err_msg = "\n\n".join(data.errors) if data.errors else "Worktree workspace is not initialized."
        fixes = data.fixes or ["Run `wt init` to create `.worktree/config.json`"]
        return Panel(
            f"{err_msg}\nFix:\n" + "\n".join(f"- {fix}" for fix in fixes),
            title="Worktree Not Initialized",
            border_style="red",
        )
    if data.status == SandboxDeleteStatus.NOT_FOUND:
        msg = data.errors[0] if data.errors else f"Sandbox '{data.sandbox_id}' not found."
        fixes = data.fixes or ["Run `wt sandbox list` to see known sandboxes"]
        return Panel(
            f"{msg}\nFix:\n" + "\n".join(f"- {fix}" for fix in fixes),
            title="Sandbox Not Found",
            border_style="red",
        )
    message = "\n\n".join(data.errors) if data.errors else "Sandbox delete failed."
    if data.fixes:
        message += "\nFix:\n" + "\n".join(f"- {fix}" for fix in data.fixes)
    return Panel(message, title="Sandbox Delete Failed", border_style="red")


class SandboxDeleteFormatter(ComponentFormatter[SandboxDeleteResult]):
    """Formatter for sandbox delete command results."""

    def to_rich(self, data: SandboxDeleteResult) -> Any:
        """Render sandbox delete success, aborted, or error state."""
        if data.status == SandboxDeleteStatus.ALREADY_CLEANED:
            return Text(f"Sandbox '{data.sandbox_id}' is already cleaned; nothing to remove.")
        if data.status == SandboxDeleteStatus.ABORTED:
            return Text("Aborted.")
        if data.status == SandboxDeleteStatus.DELETED or data.deleted:
            return Text(f"Sandbox deleted: {data.sandbox_id}", style="green")
        return _format_delete_error_panel(data)

    def to_json_serializable(self, data: SandboxDeleteResult) -> dict[str, Any]:
        """Convert SandboxDeleteResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
