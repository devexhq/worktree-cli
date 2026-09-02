from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.fs import find_worktree_root
from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
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
        *,
        dispatcher: UiDispatcher | None = None,
        output_format: str = "terminal",
    ) -> Self | None:
        """Factory to build and validate the global CLI state."""
        effective_cwd = find_worktree_root(cwd or Path.cwd())
        active_dispatcher = dispatcher if dispatcher is not None else ui_dispatcher

        load_result = load_config_result(path=effective_cwd)
        if not load_result.ok or load_result.config is None:
            active_dispatcher.dispatch(load_result, output_format=output_format)
            return None

        db = WorktreeDb(path=effective_cwd, db_rel_path=load_result.config.paths.db_path)
        return cls(cwd=effective_cwd, db=db, output=RichOutput(), config=load_result.config)
