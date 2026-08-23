"""Base repository implementation managing DB initialization and session factories."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_engine,
    get_session,
    resolve_db_path,
)
from worktree.core.db.migrations import init_database


class BaseRepository:
    """Base repository providing SQLModel session lifecycle and lazy database initialization."""

    def __init__(
        self,
        path: Path | None = None,
        db_rel_path: str = DEFAULT_DB_REL_PATH,
        db_path: Path | None = None,
        auto_init: bool = True,
        db_engine: Engine | None = None,
    ) -> None:
        self.path = path
        self.cwd = path
        self.db_rel_path = db_rel_path
        self._db_path = db_path
        self._auto_init = auto_init
        self._initialized = False
        self._db_engine: Engine | None = db_engine

    @property
    def db_path(self) -> Path:
        """Lazy-resolved database file path."""
        if self._db_path is None:
            if self.path is None:
                raise ValueError("Repository path must be provided when db_path is omitted.")
            self._db_path = resolve_db_path(self.path, self.db_rel_path)
        return self._db_path

    @property
    def db_engine(self) -> Engine:
        """SQLAlchemy / SQLModel Engine bound to db_path."""
        if self._db_engine is None:
            self._db_engine = get_engine(self.db_path)
        return self._db_engine

    @property
    def engine(self) -> Engine:
        """Alias to db_engine."""
        return self.db_engine

    @contextmanager
    def session(self) -> Generator[Session]:
        """Create and yield a new SQLModel session, running migrations lazily if auto_init is enabled."""
        if self._auto_init:
            self._ensure_initialized()
        with get_session(self.db_engine) as sess:
            yield sess

    def init_db(self) -> Path:
        """Explicitly run table migrations and mark repository initialized."""
        path = init_database(self.path, db_rel_path=self.db_rel_path, db_path=self._db_path)
        self._initialized = True
        return path

    def _ensure_initialized(self) -> None:
        """Trigger database schema creation if not already executed on this repository instance."""
        if not self._initialized:
            self.init_db()
