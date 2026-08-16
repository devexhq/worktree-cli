"""Unified database container for getworktree."""

from pathlib import Path

from getworktree.core.db.base import DbBase
from getworktree.core.db.catalog import CatalogDb
from getworktree.core.db.connection import DEFAULT_DB_REL_PATH
from getworktree.core.db.costs import CostsDb
from getworktree.core.db.sandboxes import SandboxesDb
from getworktree.core.db.tasks import TasksDb
from getworktree.core.db.workflows import WorkflowsDb


class WorktreeDb(DbBase):
    """Unified entry point providing access to all domain DB repositories under a single configuration."""

    def __init__(self, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH) -> None:
        super().__init__(cwd, db_rel_path)
        self.sandboxes = SandboxesDb(cwd, db_rel_path, auto_init=False)
        self.tasks = TasksDb(cwd, db_rel_path, auto_init=False)
        self.workflows = WorkflowsDb(cwd, db_rel_path, auto_init=False)
        self.catalog = CatalogDb(cwd, db_rel_path, auto_init=False)
        self.costs = CostsDb(cwd, db_rel_path, auto_init=False)

    def init_db(self) -> Path:
        """Run migrations and mark all child repositories as initialized."""
        path = super().init_db()
        self.sandboxes._initialized = True
        self.tasks._initialized = True
        self.workflows._initialized = True
        self.catalog._initialized = True
        self.costs._initialized = True
        return path
