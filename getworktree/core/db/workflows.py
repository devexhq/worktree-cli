"""CRUD helpers for workflow execution tracking in SQLite."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from getworktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
)
from getworktree.core.db.migrations import init_database
from getworktree.core.db.models import RunStatus, WorkflowRunRecord


def _workflow_run_record_from_row(row: sqlite3.Row) -> WorkflowRunRecord:
    """Map a `workflows` SQLite row to a strict `WorkflowRunRecord`."""
    return WorkflowRunRecord(
        id=row["id"],
        session_id=row["session_id"],
        workflow_name=row["workflow_name"],
        branch_name=row["branch_name"],
        status=RunStatus(row["status"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"],
    )


def insert_workflow_run(
    session_id: str,
    workflow_name: str,
    branch_name: str,
    status: RunStatus | str = RunStatus.RUNNING,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> WorkflowRunRecord:
    """Insert a workflow run record."""
    db_path = init_database(cwd, db_rel_path)
    status_str = status.value if isinstance(status, RunStatus) else str(status)
    insert_sql = """
    INSERT INTO workflows (session_id, workflow_name, branch_name, status)
    VALUES (?, ?, ?, ?);
    """
    select_sql = "SELECT * FROM workflows WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                insert_sql, (session_id, workflow_name, branch_name, status_str)
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Workflow run with session_id '{session_id}' already exists or failed constraints: {exc}"
            ) from exc

        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError(
                f"Failed to read workflow run row after insert: {session_id}"
            )
        return _workflow_run_record_from_row(row)


def get_workflow_run(
    session_id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> WorkflowRunRecord | None:
    """Return the workflow run matching ``session_id``, or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM workflows WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        return _workflow_run_record_from_row(row) if row is not None else None


def update_workflow_run_status(
    session_id: str,
    status: RunStatus | str,
    error_message: str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> WorkflowRunRecord | None:
    """Update status, optional completed_at timestamp, and error message for a workflow run."""
    db_path = init_database(cwd, db_rel_path)
    status_enum = (
        RunStatus(status)
        if isinstance(status, str) and status in RunStatus._value2member_map_
        else status
    )
    status_str = (
        status_enum.value if isinstance(status_enum, RunStatus) else str(status)
    )

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
    UPDATE workflows
    SET status = ?, completed_at = ?, error_message = ?
    WHERE session_id = ?;
    """
    select_sql = "SELECT * FROM workflows WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                update_sql, (status_str, completed_at, error_message, session_id)
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Invalid workflow status update constraint: {exc}"
            ) from exc

        if cursor.rowcount == 0:
            return None
        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        return _workflow_run_record_from_row(row) if row is not None else None


def list_workflow_runs(
    cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> list[WorkflowRunRecord]:
    """List workflow run records ordered by ``started_at`` descending."""
    db_path = init_database(cwd, db_rel_path)
    query_sql = "SELECT * FROM workflows ORDER BY started_at DESC;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql)
        rows = cursor.fetchall()
        return [_workflow_run_record_from_row(row) for row in rows]
