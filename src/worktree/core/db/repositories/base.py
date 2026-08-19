"""Base repository managing engine lifecycles, SQLModel sessions, and database migrations."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_engine,
    resolve_db_path,
)
from worktree.core.db.migrations import init_database


class BaseRepository:
    """Base repository providing SQLModel session lifecycle and lazy database initialization."""

    def __init__(
        self,
        cwd: Path | None = None,
        db_rel_path: str = DEFAULT_DB_REL_PATH,
        db_path: Path | None = None,
        auto_init: bool = True,
    ) -> None:
        self.cwd = cwd
        self.db_rel_path = db_rel_path
        self._db_path = db_path
        self._auto_init = auto_init
        self._initialized = False
        self._engine: Engine | None = None

    @property
    def db_path(self) -> Path:
        """Lazy-resolved database file path."""
        if self._db_path is None:
            self._db_path = resolve_db_path(self.cwd, self.db_rel_path)
        return self._db_path

    @property
    def engine(self) -> Engine:
        """SQLAlchemy / SQLModel Engine bound to db_path."""
        if self._engine is None:
            self._engine = get_engine(self.db_path)
        return self._engine

    def init_db(self) -> Path:
        """Run database migrations and mark initialized."""
        path = init_database(self.cwd, self.db_rel_path, db_path=self._db_path)
        self._initialized = True
        return path

    @contextmanager
    def session(self) -> Generator[Session]:
        """Context manager yielding a SQLModel Session bound to the engine, automatically initializing if needed."""
        if self._auto_init and not self._initialized:
            self.init_db()
        with Session(self.engine) as session:
            yield session
