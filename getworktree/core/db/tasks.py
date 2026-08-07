"""CRUD helpers for task execution tracking in SQLite using TasksDb repository."""

import sqlite3
from datetime import UTC, datetime

from getworktree.core.db.base import DbBase
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


class TasksDb(DbBase):
    """Repository managing task execution tracking CRUD operations in SQLite."""

    def insert(
        self,
        session_id: str,
        task_name: str,
        status: RunStatus | str = RunStatus.RUNNING,
    ) -> TaskRunRecord:
        """Insert a task run record."""
        status_str = status.value if isinstance(status, RunStatus) else str(status)
        insert_sql = """
        INSERT INTO tasks (session_id, task_name, status)
        VALUES (?, ?, ?);
        """
        select_sql = "SELECT * FROM tasks WHERE session_id = ?;"

        with self.cursor() as cursor:
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

    def get(self, session_id: str) -> TaskRunRecord | None:
        """Return the task run matching ``session_id``, or ``None``."""
        row = self.fetch_one("SELECT * FROM tasks WHERE session_id = ?;", (session_id,))
        return _task_run_record_from_row(row) if row is not None else None

    def update_status(
        self,
        session_id: str,
        status: RunStatus | str,
        error_message: str | None = None,
    ) -> TaskRunRecord | None:
        """Update status, optional completed_at timestamp, and error message for a task run."""
        status_enum = (
            RunStatus(status) if isinstance(status, str) and status in RunStatus._value2member_map_ else status
        )
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

        with self.cursor() as cursor:
            try:
                cursor.execute(update_sql, (status_str, completed_at, error_message, session_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Invalid task status update constraint: {exc}") from exc

            if cursor.rowcount == 0:
                return None
            cursor.execute("SELECT * FROM tasks WHERE session_id = ?;", (session_id,))
            row = cursor.fetchone()
            return _task_run_record_from_row(row) if row is not None else None

    def list(self) -> list[TaskRunRecord]:
        """List task run records ordered by ``started_at`` descending."""
        rows = self.fetch_all("SELECT * FROM tasks ORDER BY started_at DESC;")
        return [_task_run_record_from_row(row) for row in rows]
