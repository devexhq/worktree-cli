"""ComponentFormatter for LockWaitEvent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel

from worktree.cli.ui.events import LockWaitEvent
from worktree.common.types import ComponentFormatter


class LockWaitFormatter(ComponentFormatter[LockWaitEvent]):
    """Formatter for lock waiting notification panels."""

    def to_rich(self, data: LockWaitEvent) -> Panel:
        """Render lock waiting notification panel with yellow border."""
        pid_info = f" (PID: {data.holder_pid})" if data.holder_pid else ""
        lock_name = Path(data.lock_path).name
        return Panel.fit(
            f"[yellow]Workspace lock is currently held by another process{pid_info}.[/yellow]\n"
            f"[dim]Waiting for lock release on '{lock_name}' (timeout: {data.timeout_seconds:.1f}s)...[/dim]",
            title="[bold yellow]Lock Held[/bold yellow]",
            border_style="yellow",
        )

    def to_json_serializable(self, data: LockWaitEvent) -> dict[str, Any]:
        """Convert LockWaitEvent to dictionary for JSON serialization."""
        return data.model_dump(mode="json")
