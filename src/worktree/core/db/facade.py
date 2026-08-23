"""Unified database container for Worktree CLI."""

from pathlib import Path

from sqlalchemy import Engine

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_engine,
    resolve_db_path,
)
from worktree.core.db.migrations import init_database
from worktree.core.db.repositories.catalog import CatalogRepository
from worktree.core.db.repositories.costs import CostsRepository
from worktree.core.db.repositories.runs import RunsRepository
from worktree.core.db.repositories.sandboxes import SandboxesRepository


class WorktreeDb:
    """Unified entry point providing access to all domain DB repositories under a single configuration."""

    def __init__(
        self,
        path: Path,
        db_rel_path: str = DEFAULT_DB_REL_PATH,
        db_engine: Engine | None = None,
    ) -> None:
        self.path = path.resolve()
        self.cwd = self.path
        self.db_rel_path = db_rel_path
        self._db_engine = db_engine
        self._sandboxes: SandboxesRepository | None = None
        self._runs: RunsRepository | None = None
        self._catalog: CatalogRepository | None = None
        self._costs: CostsRepository | None = None

    @property
    def db_engine(self) -> Engine:
        """SQLAlchemy / SQLModel Engine bound to resolved database path."""
        if self._db_engine is None:
            self._db_engine = get_engine(resolve_db_path(self.path, self.db_rel_path))
        return self._db_engine

    @property
    def engine(self) -> Engine:
        """Alias to db_engine for compatibility."""
        return self.db_engine

    @property
    def sandboxes(self) -> SandboxesRepository:
        """Repository managing sandbox worktrees and metadata."""
        if self._sandboxes is None:
            self._sandboxes = SandboxesRepository(
                self.path, db_rel_path=self.db_rel_path, auto_init=True, db_engine=self.db_engine
            )
        return self._sandboxes

    @property
    def runs(self) -> RunsRepository:
        """Repository managing task and workflow execution runs."""
        if self._runs is None:
            self._runs = RunsRepository(
                self.path, db_rel_path=self.db_rel_path, auto_init=True, db_engine=self.db_engine
            )
        return self._runs

    @property
    def catalog(self) -> CatalogRepository:
        """Repository managing indexed blueprint definitions."""
        if self._catalog is None:
            self._catalog = CatalogRepository(
                self.path, db_rel_path=self.db_rel_path, auto_init=True, db_engine=self.db_engine
            )
        return self._catalog

    @property
    def costs(self) -> CostsRepository:
        """Repository managing tracked token costs."""
        if self._costs is None:
            self._costs = CostsRepository(
                self.path, db_rel_path=self.db_rel_path, auto_init=True, db_engine=self.db_engine
            )
        return self._costs

    def init_db(self) -> Path:
        """Run migrations and mark all child repositories as initialized."""
        path = init_database(self.path, self.db_rel_path)
        self.sandboxes._initialized = True
        self.runs._initialized = True
        self.catalog._initialized = True
        self.costs._initialized = True
        return path
