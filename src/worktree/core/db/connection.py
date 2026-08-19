"""SQLite connection, engine factory, and path resolution helpers."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Session, create_engine

DEFAULT_DB_REL_PATH = ".worktree/data.db"


def resolve_db_path(cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH) -> Path:
    """Resolve database path relative to project root, ensuring target parent directory exists."""
    base_dir = (cwd or Path.cwd()).resolve()
    db_path = base_dir / db_rel_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _set_sqlite_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
    """Enable WAL mode and busy timeout for safe concurrent CLI + Desktop access."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


def get_engine(db_path: Path) -> Engine:
    """Create a SQLModel/SQLAlchemy engine configured with SQLite WAL pragmas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


@contextmanager
def get_session(engine: Engine) -> Generator[Session]:
    """Context manager offering clean database session setup and safe teardown."""
    with Session(engine) as session:
        yield session


@contextmanager
def get_db_connection(db_path: Path) -> Generator[sqlite3.Connection]:
    """Context manager offering clean database connection setup and safe teardown."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
