# src/worktree/cli/context.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from worktree.common.utils import RichOutput
from worktree.core.db.facade import WorktreeDb


class Context(BaseModel):
    """Global CLI context."""

    model_config = {"extra": "forbid", "strict": True, "arbitrary_types_allowed": True}

    db: WorktreeDb
    cwd: Path
    output: RichOutput = Field(default_factory=RichOutput)


# Backward compatibility alias
CliContext = Context


def get_cli_context(cwd: Path | None = None) -> Context:
    """Factory to build the global application state."""
    effective_cwd = cwd or Path.cwd()

    # If you ever need to load a config.toml, set up a global logger,
    # or handle a missing .worktree directory, you do it here, exactly once.
    db = WorktreeDb(path=effective_cwd)
    output = RichOutput()

    return Context(cwd=effective_cwd, db=db, output=output)
