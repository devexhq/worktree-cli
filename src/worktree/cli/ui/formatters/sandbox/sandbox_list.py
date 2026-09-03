"""ComponentFormatter for SandboxListResult."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.formatters.sandbox.common import build_sandbox_table
from worktree.common.types import ComponentFormatter
from worktree.core.sandbox.models import SandboxListResult


class SandboxListFormatter(ComponentFormatter[SandboxListResult]):
    """Formatter for sandbox list command results."""

    def to_rich(self, data: SandboxListResult) -> Any:
        """Render sandbox summary list table or empty state."""
        if not data.ok:
            err_msg = "\n\n".join(data.errors) if data.errors else "Worktree workspace is not initialized."
            fixes = data.fixes or ["Run `wt init` to create `.worktree/config.json`"]
            return Panel(
                f"{err_msg}\nFix:\n" + "\n".join(f"- {fix}" for fix in fixes),
                title="Worktree Not Initialized",
                border_style="red",
            )

        if not data.sandboxes:
            return Text("No sandboxes found.")

        return build_sandbox_table(data.sandboxes)

    def to_json_serializable(self, data: SandboxListResult) -> dict[str, Any]:
        """Convert SandboxListResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
