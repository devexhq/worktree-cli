# src/worktree/core/context.py
from pathlib import Path

from worktree.core.config.models import CliContext
from worktree.core.db.facade import WorktreeDb


def get_cli_context(cwd: Path | None = None) -> CliContext:
    """Factory to build the global application state."""
    effective_cwd = cwd or Path.cwd()

    # If you ever need to load a config.toml, set up a global logger,
    # or handle a missing .worktree directory, you do it here, exactly once.
    db = WorktreeDb(cwd=effective_cwd)

    return CliContext(cwd=effective_cwd, db=db)
