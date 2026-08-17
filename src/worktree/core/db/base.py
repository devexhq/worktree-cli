"""Base database class managing path resolution, initialization, connection lifecycles, and query execution."""

import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    resolve_db_path,
)
from worktree.core.db.migrations import init_database


class DbBase:
    """Base class for database repositories providing path resolution, cursor management, and execution helpers."""

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

    @property
    def db_path(self) -> Path:
        """Lazy-resolved database file path."""
        if self._db_path is None:
            self._db_path = resolve_db_path(self.cwd, self.db_rel_path)
        return self._db_path

    def init_db(self) -> Path:
        """Run database migrations and mark initialized."""
        path = init_database(self.cwd, self.db_rel_path)
        self._initialized = True
        return path

    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor]:
        """Context manager offering clean sqlite3.Cursor setup, transaction commit, and teardown."""
        if self._auto_init and not self._initialized:
            self.init_db()

        with get_db_connection(self.db_path) as conn:
            yield conn.cursor()

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        """Execute query and fetch a single matching row, or None."""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """Execute query and fetch all matching rows."""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Execute DML statement and return affected rowcount."""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    def execute_insert(self, sql: str, params: Sequence[Any] = ()) -> int | None:
        """Execute insert statement and return lastrowid primary key."""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid
