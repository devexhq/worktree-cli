"""Database migration DDL statements and database initialization logic."""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    resolve_db_path,
)

# Schema migration DDL for tracking AI model token costs (retained for backward compatibility)
CREATE_WORKFLOW_COSTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_costs (
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
CREATE INDEX IF NOT EXISTS idx_workflow_costs_session ON workflow_costs(session_id);
CREATE INDEX IF NOT EXISTS idx_workflow_costs_created ON workflow_costs(created_at);
"""

# Schema migration DDL for durable sandbox metadata (retained for backward compatibility)
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

# Schema migration DDL for catalog indexing (retained for backward compatibility)
CREATE_CATALOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha TEXT UNIQUE NOT NULL,
    item_type TEXT NOT NULL CHECK(item_type IN ('workflow', 'task', 'step')),
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_catalog_sha ON catalog(sha);
CREATE INDEX IF NOT EXISTS idx_catalog_type ON catalog(item_type);
CREATE INDEX IF NOT EXISTS idx_catalog_path ON catalog(path);
"""

_RUN_STATUS_CHECK = "('running', 'completed', 'failed', 'cancelled', 'paused')"
_RUN_KIND_CHECK = "('task', 'workflow')"

# Schema migration DDL for unified run execution tracking (retained for backward compatibility)
CREATE_RUNS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    blueprint_name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN {_RUN_KIND_CHECK}),
    branch_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN {_RUN_STATUS_CHECK}),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    checkpoint_json TEXT
);
"""

CREATE_RUNS_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
"""


def _table_ddl(conn: sqlite3.Connection, table: str) -> str | None:
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = cursor.fetchone()
    return row[0] if row is not None else None


def _migrate_legacy_runs(conn: sqlite3.Connection) -> None:
    """Copy rows from legacy workflows and tasks tables into runs if they exist."""
    if _table_ddl(conn, "workflows") is not None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(workflows)")}
        chk = "checkpoint_json" if "checkpoint_json" in columns else "NULL"
        conn.execute(
            f"""
            INSERT OR IGNORE INTO runs (session_id, blueprint_name, kind, branch_name, status, started_at, completed_at, error_message, checkpoint_json)
            SELECT session_id, workflow_name, 'workflow', branch_name, status, started_at, completed_at, error_message, {chk}
            FROM workflows;
            """
        )
    if _table_ddl(conn, "tasks") is not None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        chk = "checkpoint_json" if "checkpoint_json" in columns else "NULL"
        conn.execute(
            f"""
            INSERT OR IGNORE INTO runs (session_id, blueprint_name, kind, branch_name, status, started_at, completed_at, error_message, checkpoint_json)
            SELECT session_id, task_name, 'task', '', status, started_at, completed_at, error_message, {chk}
            FROM tasks;
            """
        )


def _is_legacy_unversioned_db(db_path: Path) -> bool:
    """Check if the database contains existing tables but no alembic_version table."""
    if not db_path.exists():
        return False
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        if cursor.fetchone() is not None:
            return False
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('runs', 'sandboxes', 'catalog', 'workflow_costs')"
        )
        return cursor.fetchone() is not None


def init_database(
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
    db_path: Path | None = None,
) -> Path:
    """Run table migrations and initialize local SQLite database layout."""
    target_path = db_path if db_path is not None else resolve_db_path(cwd, db_rel_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    is_legacy = _is_legacy_unversioned_db(target_path)

    alembic_cfg = Config()
    alembic_dir = Path(__file__).parent / "alembic"
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{target_path}")

    if is_legacy:
        command.stamp(alembic_cfg, "0001_initial_schema")

    command.upgrade(alembic_cfg, "head")

    with get_db_connection(target_path) as conn:
        _migrate_legacy_runs(conn)

    return target_path
