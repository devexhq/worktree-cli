"""getworktree/core/db.py.

Handles offline SQLite connection pooling, database migrations, and financial token
usage tracking for automated agent loops.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

DEFAULT_DB_REL_PATH = ".worktree/data.db"

# Schema migration DDL for tracking AI model token costs
CREATE_LOOP_COSTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS loop_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_usd_cost REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_loop_costs_session ON loop_costs(session_id);
CREATE INDEX IF NOT EXISTS idx_loop_costs_created ON loop_costs(created_at);
"""

# Schema migration DDL for durable sandbox metadata
CREATE_SANDBOXES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sandboxes (
    id TEXT PRIMARY KEY,
    name TEXT,
    branch_name TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    sandbox_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'merged', 'cleaned', 'conflict')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sandboxes_status ON sandboxes(status);
"""


class SandboxStatus(StrEnum):
    """Lifecycle status for a persisted sandbox metadata row."""

    ACTIVE = "active"
    MERGED = "merged"
    CLEANED = "cleaned"
    CONFLICT = "conflict"


class SandboxRecord(BaseModel):
    """Row shape for the local `sandboxes` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: str
    name: str | None = None
    branch_name: str
    base_commit: str
    sandbox_path: Path
    status: SandboxStatus
    created_at: str
    updated_at: str


def resolve_db_path(
    cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> Path:
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


def init_database(
    cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> Path:
    """Run table migrations and initialize local SQLite database layout."""
    db_path = resolve_db_path(cwd, db_rel_path)
    with get_db_connection(db_path) as conn:
        conn.executescript(CREATE_LOOP_COSTS_TABLE_SQL)
        conn.executescript(CREATE_SANDBOXES_TABLE_SQL)
    return db_path


def _sandbox_record_from_row(row: sqlite3.Row) -> SandboxRecord:
    """Map a `sandboxes` SQLite row to a strict `SandboxRecord`."""
    return SandboxRecord(
        id=row["id"],
        name=row["name"],
        branch_name=row["branch_name"],
        base_commit=row["base_commit"],
        sandbox_path=Path(row["sandbox_path"]),
        status=SandboxStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def insert_sandbox(
    id: str,
    branch_name: str,
    base_commit: str,
    sandbox_path: Path,
    name: str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> SandboxRecord:
    """Insert a sandbox metadata row with status ``active``.

    Returns:
        The inserted `SandboxRecord`, including DB-assigned timestamps.

    Raises:
        ValueError: If a row with the same ``id`` already exists.
    """
    db_path = init_database(cwd, db_rel_path)
    insert_sql = """
    INSERT INTO sandboxes (
        id, name, branch_name, base_commit, sandbox_path, status
    ) VALUES (?, ?, ?, ?, ?, ?);
    """
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                insert_sql,
                (
                    id,
                    name,
                    branch_name,
                    base_commit,
                    str(sandbox_path),
                    SandboxStatus.ACTIVE.value,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Sandbox with id '{id}' already exists") from exc
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        if row is None:  # pragma: no cover - insert just succeeded
            raise RuntimeError(f"Failed to read sandbox row after insert: {id}")
        return _sandbox_record_from_row(row)


def get_sandbox(
    id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> SandboxRecord | None:
    """Return the sandbox row for ``id``, or ``None`` when missing."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        return _sandbox_record_from_row(row) if row is not None else None


def list_sandboxes(
    status: SandboxStatus | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> list[SandboxRecord]:
    """List sandbox rows ordered by ``created_at`` descending.

    When ``status`` is set, only rows with that status are returned.
    """
    db_path = init_database(cwd, db_rel_path)

    if status is None:
        query_sql = "SELECT * FROM sandboxes ORDER BY created_at DESC;"
        params: tuple[object, ...] = ()
    else:
        query_sql = "SELECT * FROM sandboxes WHERE status = ? ORDER BY created_at DESC;"
        params = (status.value,)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
        return [_sandbox_record_from_row(row) for row in rows]


def update_sandbox_status(
    id: str,
    status: SandboxStatus,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> SandboxRecord | None:
    """Update sandbox status and ``updated_at``; return the row or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    update_sql = """
    UPDATE sandboxes
    SET status = ?, updated_at = ?
    WHERE id = ?;
    """
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(update_sql, (status.value, now_utc, id))
        if cursor.rowcount == 0:
            return None
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        return _sandbox_record_from_row(row) if row is not None else None


def delete_sandbox_row(
    id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> bool:
    """Hard-delete a sandbox metadata row. Returns whether a row was removed."""
    db_path = init_database(cwd, db_rel_path)
    delete_sql = "DELETE FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(delete_sql, (id,))
        return cursor.rowcount > 0


def record_token_usage(
    session_id: str,
    branch_name: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_usd_cost: float,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> int | None:
    """Log token consumption and dollar costs for an execution step.

    Returns the auto-incremented primary key ID of the inserted record.
    """
    db_path = init_database(cwd, db_rel_path)
    total_tokens = prompt_tokens + completion_tokens
    now_utc = datetime.now(UTC).isoformat()

    insert_sql = """
    INSERT INTO loop_costs (
        session_id, branch_name, model_id, prompt_tokens,
        completion_tokens, total_tokens, estimated_usd_cost, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            insert_sql,
            (
                session_id,
                branch_name,
                model_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                estimated_usd_cost,
                now_utc,
            ),
        )
        return cursor.lastrowid


def get_session_total_cost(
    session_id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> dict[str, float]:
    """Calculate aggregated token counts and dollar spend for a specific execution loop session."""
    db_path = init_database(cwd, db_rel_path)

    query_sql = """
    SELECT
        COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
        COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
        COALESCE(SUM(total_tokens), 0) AS total_tokens,
        COALESCE(SUM(estimated_usd_cost), 0.0) AS total_usd_cost
    FROM loop_costs
    WHERE session_id = ?;
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql, (session_id,))
        row = cursor.fetchone()
        return (
            dict(row)
            if row
            else {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "total_usd_cost": 0.0,
            }
        )
