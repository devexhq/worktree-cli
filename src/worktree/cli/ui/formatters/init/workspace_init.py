"""ComponentFormatter for WorkspaceInitResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.text import Text

from worktree.cli.ui.formatters.init.common import (
    render_bootstrap_lines,
    render_config_lines,
    render_failure_panel,
    render_seed_lines,
)
from worktree.common.types import ComponentFormatter
from worktree.core.bootstrap import WorkspaceInitResult


class WorkspaceInitFormatter(ComponentFormatter[WorkspaceInitResult]):
    """Formatter for workspace initialization results."""

    def to_rich(self, data: WorkspaceInitResult) -> Any:
        """Render initialization summary, repair details, or failure panels."""
        failure_panel = render_failure_panel(data)
        if failure_panel is not None:
            return failure_panel

        cwd = (
            data.bootstrap_result.root_path.parent
            if data.bootstrap_result is not None and data.bootstrap_result.root_path
            else Path.cwd()
        )

        renderables: list[Any] = [Text("")]
        if data.bootstrap_result is not None:
            renderables.extend(render_bootstrap_lines(data.bootstrap_result, cwd))
        if data.config_result is not None:
            renderables.extend(render_config_lines(data.config_result, cwd))
        if data.seed_result is not None:
            renderables.extend(render_seed_lines(data.seed_result, cwd))
        renderables.append(Text(""))
        renderables.append(
            Text.from_markup(
                "[bold dim]Next: run [bold cyan]wt config show[/bold cyan] or [bold cyan]wt workflow list[/bold cyan][/bold dim]"
            )
        )
        return Group(*renderables)

    def to_json_serializable(self, data: WorkspaceInitResult) -> dict[str, Any]:
        """Convert WorkspaceInitResult to primitive dictionary for JSON serialization."""
        return data.model_dump(mode="json")


InitOutcomeFormatter = WorkspaceInitFormatter
