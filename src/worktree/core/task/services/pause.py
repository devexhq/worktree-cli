"""Task-run adapter that persists durable pause checkpoints."""

from __future__ import annotations

from pathlib import Path

from worktree.core.db import RunsRepository, RunStatus
from worktree.core.runtime import RunCheckpoint


class TaskPauseStore:
    """``RunPauseStore`` implementation backed by ``RunsRepository``."""

    def __init__(self, cwd: Path, session_id: str) -> None:
        self._db = RunsRepository(cwd)
        self._session_id = session_id

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        """Write checkpoint JSON and set the task row to paused."""
        self._db.save_pause(
            self._session_id,
            checkpoint.model_dump_json(),
            checkpoint.diagnostic,
        )

    def clear_pause(self) -> None:
        """Mark the task row running after an in-process prompt returns."""
        self._db.update_status(self._session_id, RunStatus.RUNNING)
