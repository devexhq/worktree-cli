"""Database migration execution and database initialization logic."""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    resolve_db_path,
)


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
