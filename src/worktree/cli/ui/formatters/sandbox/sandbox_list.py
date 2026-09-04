"""ComponentFormatter for SandboxListResult."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from worktree.cli.ui.formatters.common import build_error_panel
from worktree.cli.ui.formatters.sandbox.common import build_sandbox_table
from worktree.common.types import ComponentFormatter
from worktree.core.sandbox.models import SandboxListResult


class SandboxListFormatter(ComponentFormatter[SandboxListResult]):
    """Formatter for sandbox list command results."""

    def to_rich(self, data: SandboxListResult) -> Any:
        """Render sandbox summary list table or empty state."""
        if not data.ok:
            fixes = data.fixes or ["Run `wt init` to create `.worktree/config.json`"]
            return build_error_panel(
                "Worktree Not Initialized",
                data.errors,
                "Worktree workspace is not initialized.",
                fixes,
            )

        if not data.sandboxes:
            return Text("No sandboxes found.")

        return build_sandbox_table(data.sandboxes)

    def to_json_serializable(self, data: SandboxListResult) -> dict[str, Any]:
        """Convert SandboxListResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
