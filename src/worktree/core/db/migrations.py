"""Database migration DDL statements and database initialization logic."""

import sqlite3
from pathlib import Path

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    resolve_db_path,
)

# Schema migration DDL for tracking AI model token costs
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

# Schema migration DDL for catalog indexing
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

# Schema migration DDL for workflow execution tracking
CREATE_WORKFLOWS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    workflow_name TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN {_RUN_STATUS_CHECK}),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    checkpoint_json TEXT
);
"""

CREATE_WORKFLOWS_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_workflows_session ON workflows(session_id);
CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
"""

# Schema migration DDL for task execution tracking
CREATE_TASKS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    task_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN {_RUN_STATUS_CHECK}),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    checkpoint_json TEXT
);
"""

CREATE_TASKS_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
"""

_WORKFLOW_COPY_COLUMNS = (
    "id, session_id, workflow_name, branch_name, status, started_at, completed_at, error_message, checkpoint_json"
)
_TASK_COPY_COLUMNS = "id, session_id, task_name, status, started_at, completed_at, error_message, checkpoint_json"


def _table_ddl(conn: sqlite3.Connection, table: str) -> str | None:
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = cursor.fetchone()
    return row[0] if row is not None else None


def _add_checkpoint_column(conn: sqlite3.Connection, table: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if "checkpoint_json" not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN checkpoint_json TEXT")


def _rebuild_run_table(
    conn: sqlite3.Connection,
    table: str,
    create_sql: str,
    copy_columns: str,
    indexes_sql: str,
) -> None:
    tmp = f"{table}__new"
    create_tmp = create_sql.replace(f"CREATE TABLE IF NOT EXISTS {table}", f"CREATE TABLE {tmp}", 1)
    conn.executescript(create_tmp)
    conn.execute(f"INSERT INTO {tmp} ({copy_columns}) SELECT {copy_columns} FROM {table}")
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {tmp} RENAME TO {table}")
    conn.executescript(indexes_sql)


def _migrate_run_table(
    conn: sqlite3.Connection,
    table: str,
    create_sql: str,
    copy_columns: str,
    indexes_sql: str,
) -> None:
    ddl = _table_ddl(conn, table)
    if ddl is None:
        return
    _add_checkpoint_column(conn, table)
    if "'paused'" in ddl:
        return
    _rebuild_run_table(conn, table, create_sql, copy_columns, indexes_sql)


def init_database(cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH) -> Path:
    """Run table migrations and initialize local SQLite database layout."""
    db_path = resolve_db_path(cwd, db_rel_path)
    with get_db_connection(db_path) as conn:
        conn.executescript(CREATE_WORKFLOW_COSTS_TABLE_SQL)
        conn.executescript(CREATE_SANDBOXES_TABLE_SQL)
        conn.executescript(CREATE_CATALOG_TABLE_SQL)
        conn.executescript(CREATE_WORKFLOWS_TABLE_SQL)
        conn.executescript(CREATE_WORKFLOWS_INDEXES_SQL)
        conn.executescript(CREATE_TASKS_TABLE_SQL)
        conn.executescript(CREATE_TASKS_INDEXES_SQL)
        _migrate_run_table(
            conn, "workflows", CREATE_WORKFLOWS_TABLE_SQL, _WORKFLOW_COPY_COLUMNS, CREATE_WORKFLOWS_INDEXES_SQL
        )
        _migrate_run_table(conn, "tasks", CREATE_TASKS_TABLE_SQL, _TASK_COPY_COLUMNS, CREATE_TASKS_INDEXES_SQL)
    return db_path
