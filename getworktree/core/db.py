"""getworktree/core/db.py.

Handles offline SQLite connection pooling, database migrations, and financial token
usage tracking for automated agent loops.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DB_REL_PATH = ".worktree/token_audit.db"

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


def resolve_db_path(
    cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> Path:
    """Resolve database path relative to project root, ensuring target parent directory exists."""
    base_dir = (cwd or Path.cwd()).resolve()
    db_path = base_dir / db_rel_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@contextmanager
def get_db_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
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
    return db_path


def record_token_usage(
    session_id: str,
    branch_name: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_usd_cost: float,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> int:
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
