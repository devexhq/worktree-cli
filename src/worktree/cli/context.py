from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from worktree.common.fs import find_worktree_root
from worktree.common.utils import RichOutput
from worktree.core.config.loader import ConfigLoadStatus, load_config_result
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
        effective_cwd = find_worktree_root(cwd or Path.cwd())
        output = RichOutput()

        # Config validation
        load_result = load_config_result(path=effective_cwd)
        if not load_result.ok:
            if load_result.status == ConfigLoadStatus.NOT_FOUND:
                output.add_error("Worktree workspace is not initialized.")
                output.add_line("Hint: Run 'wt init' to initialize Worktree in this repository.")
            else:
                message = (
                    "\n\n".join(load_result.errors)
                    if load_result.errors
                    else f"Configuration failed to load ({load_result.status.value.upper()})."
                )
                output.add_error_panel("Invalid Worktree Configuration", message)
            output.print()
            return None

        db = WorktreeDb(path=effective_cwd)
        return cls(cwd=effective_cwd, db=db, output=output)
