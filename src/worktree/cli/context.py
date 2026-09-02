from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from worktree.common.filesystem import Filesystem
from worktree.common.utils import RichOutput
from worktree.core.config import Config
from worktree.core.config.models import WorktreeConfig
from worktree.core.db.facade import WorktreeDb


@dataclass
class CliContext:
    """Core environment state for Worktree CLI."""

    cwd: Path
    db: WorktreeDb
    output: RichOutput
    config: WorktreeConfig | None = None
    fs: Filesystem = field(default_factory=Filesystem)

    @classmethod
    def build(
        cls,
        cwd: Path | None = None,
        *,
        path: Path | None = None,
    ) -> Self:
        """Factory to build the global CLI state."""
        target_path = path if path is not None else cwd
        fs = Filesystem.configure(target_path)
        config = Config.configure(target_path)
        effective_cwd = fs.root_dir
        db = WorktreeDb(path=effective_cwd, db_rel_path=config.paths.db_path)
        return cls(cwd=effective_cwd, db=db, output=RichOutput(), config=config._loaded_config, fs=fs)
