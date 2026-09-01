"""Status domain facade."""

from __future__ import annotations

from pathlib import Path

from worktree.core.status.models import WorktreeStatusResult


class Status:
    """Unified entrypoint for workspace status and runtime health collection."""

    def __init__(self, path: Path = Path(".")) -> None:
        self.path = path.resolve()
        self.cwd = self.path

    def collect(self) -> WorktreeStatusResult:
        """Collect and return full workspace health and telemetry status."""
        from worktree.core.status.services.collector import collect_status

        return collect_status(self.path)

    @classmethod
    def collect_at(cls, path: Path) -> WorktreeStatusResult:
        """Helper to collect workspace status at specified path."""
        return cls(path).collect()
