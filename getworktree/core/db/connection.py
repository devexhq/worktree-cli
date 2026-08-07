"""SQLite connection and path resolution helpers."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_REL_PATH = ".worktree/data.db"


def resolve_db_path(cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH) -> Path:
    """Resolve database path relative to project root, ensuring target parent directory exists."""
    base_dir = (cwd or Path.cwd()).resolve()
    db_path = base_dir / db_rel_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


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
