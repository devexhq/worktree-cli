"""Diff domain facade."""

from __future__ import annotations

from pathlib import Path

from worktree.core.diff.models import DiffResult
from worktree.core.diff.services import DiffService
from worktree.core.diff.writer import get_session_dir, write_session_diff


class Diff:
    """Unified entrypoint for execution run diff artifacts inspection and writing."""

    def __init__(self, path: Path = Path(".")) -> None:
        self.path = path.resolve()
        self.cwd = self.path

    def inspect(self, session_id: str | None = None) -> DiffResult:
        """Inspect and return structured diff result for a session or latest run."""
        service = DiffService(path=self.path, session_id=session_id)
        return service.collect()

    @staticmethod
    def session_dir(root: Path, session_id: str) -> Path:
        """Return the target directory for storing session artifacts."""
        return get_session_dir(root, session_id)

    @staticmethod
    def write(session_dir: Path, diff_text: str) -> Path:
        """Write session diff text to diff.patch atomically."""
        return write_session_diff(session_dir, diff_text)
