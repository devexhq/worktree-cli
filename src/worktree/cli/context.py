from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.cli.ui.events import LockWaitEvent
from worktree.common.filesystem import Filesystem
from worktree.common.lock import WorkspaceLock
from worktree.core.config import Config
from worktree.core.config.models import WorktreeConfig
from worktree.core.db.facade import WorktreeDb


def default_lock_wait_notifier(lock_path: Path, holder_pid: str | None, timeout_seconds: float) -> None:
    """Dispatch LockWaitEvent through UI dispatcher when lock contention occurs."""
    ui_dispatcher.dispatch(
        LockWaitEvent(
            lock_path=str(lock_path),
            holder_pid=holder_pid,
            timeout_seconds=timeout_seconds,
        )
    )


@dataclass
class CliContext:
    """Core environment state for Worktree CLI."""

    cwd: Path
    db: WorktreeDb
    config: WorktreeConfig | None = None
    fs: Filesystem = field(default_factory=Filesystem)
    on_lock_wait: Callable[[Path, str | None, float], None] | None = None

    def __post_init__(self) -> None:
        notifier = self.on_lock_wait or default_lock_wait_notifier
        WorkspaceLock.set_default_on_wait(notifier)

    @classmethod
    def build(
        cls,
        cwd: Path | None = None,
        *,
        path: Path | None = None,
        on_lock_wait: Callable[[Path, str | None, float], None] | None = None,
    ) -> Self:
        """Factory to build the global CLI state."""
        target_path = path if path is not None else cwd
        fs = Filesystem.configure(target_path)
        config = Config.configure(target_path)
        effective_cwd = fs.root_dir
        db = WorktreeDb(path=effective_cwd, db_rel_path=config.paths.db_path)
        return cls(cwd=effective_cwd, db=db, config=config._loaded_config, fs=fs, on_lock_wait=on_lock_wait)
