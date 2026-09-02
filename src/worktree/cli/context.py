from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from worktree.common.fs import find_worktree_root
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

    @classmethod
    def build(
        cls,
        cwd: Path | None = None,
    ) -> Self:
        """Factory to build the global CLI state."""
        effective_cwd = find_worktree_root(cwd or Path.cwd())
        config = Config(effective_cwd)
        db = WorktreeDb(path=effective_cwd, db_rel_path=config.paths.db_path)
        return cls(cwd=effective_cwd, db=db, output=RichOutput(), config=config._loaded_config)
