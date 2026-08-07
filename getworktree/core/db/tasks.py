"""CRUD helpers for task execution tracking in SQLite."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from getworktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
)
from getworktree.core.db.migrations import init_database
from getworktree.core.db.models import RunStatus, TaskRunRecord


def _task_run_record_from_row(row: sqlite3.Row) -> TaskRunRecord:
    """Map a `tasks` SQLite row to a strict `TaskRunRecord`."""
    return TaskRunRecord(
        id=row["id"],
        session_id=row["session_id"],
        task_name=row["task_name"],
        status=RunStatus(row["status"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"],
    )


def insert_task_run(
    session_id: str,
    task_name: str,
    status: RunStatus | str = RunStatus.RUNNING,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> TaskRunRecord:
    """Insert a task run record."""
    db_path = init_database(cwd, db_rel_path)
    status_str = status.value if isinstance(status, RunStatus) else str(status)
    insert_sql = """
    INSERT INTO tasks (session_id, task_name, status)
    VALUES (?, ?, ?);
    """
    select_sql = "SELECT * FROM tasks WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(insert_sql, (session_id, task_name, status_str))
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Task run with session_id '{session_id}' already exists or failed constraints: {exc}"
            ) from exc

        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError(f"Failed to read task run row after insert: {session_id}")
        return _task_run_record_from_row(row)


def get_task_run(
    session_id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> TaskRunRecord | None:
    """Return the task run matching ``session_id``, or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM tasks WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        return _task_run_record_from_row(row) if row is not None else None


def update_task_run_status(
    session_id: str,
    status: RunStatus | str,
    error_message: str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> TaskRunRecord | None:
    """Update status, optional completed_at timestamp, and error message for a task run."""
    db_path = init_database(cwd, db_rel_path)
    status_enum = RunStatus(status) if isinstance(status, str) and status in RunStatus._value2member_map_ else status
    status_str = status_enum.value if isinstance(status_enum, RunStatus) else str(status)

    completed_at = (
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if status_str
        in (
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        )
        else None
    )

    update_sql = """
    UPDATE tasks
    SET status = ?, completed_at = ?, error_message = ?
    WHERE session_id = ?;
    """
    select_sql = "SELECT * FROM tasks WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(update_sql, (status_str, completed_at, error_message, session_id))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Invalid task status update constraint: {exc}") from exc

        if cursor.rowcount == 0:
            return None
        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        return _task_run_record_from_row(row) if row is not None else None


def list_task_runs(cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH) -> list[TaskRunRecord]:
    """List task run records ordered by ``started_at`` descending."""
    db_path = init_database(cwd, db_rel_path)
    query_sql = "SELECT * FROM tasks ORDER BY started_at DESC;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql)
        rows = cursor.fetchall()
        return [_task_run_record_from_row(row) for row in rows]
