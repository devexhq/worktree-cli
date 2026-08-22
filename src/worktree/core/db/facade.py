"""Unified database container for Worktree CLI."""

from pathlib import Path

from worktree.core.db.base import DbBase
from worktree.core.db.connection import DEFAULT_DB_REL_PATH
from worktree.core.db.costs import CostsDb
from worktree.core.db.repositories.catalog import CatalogRepository
from worktree.core.db.repositories.runs import RunsRepository
from worktree.core.db.repositories.sandboxes import SandboxesRepository


class WorktreeDb(DbBase):
    """Unified entry point providing access to all domain DB repositories under a single configuration."""

    def __init__(self, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH) -> None:
        super().__init__(cwd, db_rel_path)
        self.sandboxes = SandboxesRepository(cwd, db_rel_path, auto_init=False)
        self.runs = RunsRepository(cwd, db_rel_path, auto_init=False)
        self.catalog = CatalogRepository(cwd, db_rel_path, auto_init=False)
        self.costs = CostsDb(cwd, db_rel_path, auto_init=False)

    def init_db(self) -> Path:
        """Run migrations and mark all child repositories as initialized."""
        path = super().init_db()
        self.sandboxes._initialized = True
        self.runs._initialized = True
        self.catalog._initialized = True
        self.costs._initialized = True
        return path
