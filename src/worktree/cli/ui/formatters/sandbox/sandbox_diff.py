"""ComponentFormatter for SandboxDiffResult."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from worktree.common.types import ComponentFormatter
from worktree.core.sandbox.models import SandboxDiffResult, SandboxDiffStatus


class SandboxDiffFormatter(ComponentFormatter[SandboxDiffResult]):
    """Formatter for sandbox diff command results."""

    def to_rich(self, data: SandboxDiffResult) -> Any:
        """Render sandbox diff text, stat summary, or error panel."""
        if data.status == SandboxDiffStatus.EMPTY_DIFF:
            return Text(f"Sandbox '{data.sandbox_id}' has no changes compared to base commit.")
        if not data.ok:
            message = "\n\n".join(data.errors) if data.errors else "Failed to generate diff."
            if data.fixes:
                message += "\nFix:\n" + "\n".join(f"- {fix}" for fix in data.fixes)
            return Panel(message, title="Sandbox Diff Failed", border_style="red")
        if data.stat_text:
            return Text(data.stat_text.strip())
        return Syntax(data.diff_text.strip(), "diff", word_wrap=True)

    def to_json_serializable(self, data: SandboxDiffResult) -> dict[str, Any]:
        """Convert SandboxDiffResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")
