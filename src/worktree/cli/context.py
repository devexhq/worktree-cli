# src/worktree/cli/context.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.db.facade import WorktreeDb


@dataclass
class CliContext:
    """Core environment state for Worktree CLI."""

    cwd: Path
    db: WorktreeDb
    output: RichOutput

    @classmethod
    def build(cls, cwd: Path | None = None) -> Self | None:
        """Factory to build and validate the global CLI state."""
        effective_cwd = cwd or Path.cwd()
        output = RichOutput()

        # Config validation
        load_result = load_config_result(path=effective_cwd)
        if not load_result.ok:
            output.add_error("Not initialized or invalid config.")
            output.add_line("Hint: Run wt init")
            output.print()
            return None

        db = WorktreeDb(path=effective_cwd)
        return cls(cwd=effective_cwd, db=db, output=output)
