"""CRUD helpers for run tracking in SQLite using RunTrackingDb generic repository."""

import sqlite3
from datetime import UTC, datetime
from typing import ClassVar, cast

from pydantic import BaseModel

from worktree.core.db.base import DbBase
from worktree.core.db.models import RunStatus


class RunTrackingDb[T: BaseModel](DbBase):
    """Generic CRUD repository base for per-domain run-tracking tables in SQLite."""

    table: ClassVar[str]
    record_cls: ClassVar[type[BaseModel]]
    extra_columns: ClassVar[tuple[str, ...]] = ()

    def _record_from_row(self, row: sqlite3.Row) -> T:
        """Map a SQLite row to a strict domain run record using ``record_cls``."""
        kwargs: dict[str, str | int | RunStatus | None] = {
            "id": row["id"],
            "session_id": row["session_id"],
            "status": RunStatus(row["status"]),
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "error_message": row["error_message"],
            "checkpoint_json": row["checkpoint_json"] if "checkpoint_json" in row.keys() else None,
        }
        for col in self.extra_columns:
            kwargs[col] = row[col]
        return cast(T, self.record_cls.model_validate(kwargs))

    def insert(
        self,
        session_id: str,
        *,
        status: RunStatus | str = RunStatus.RUNNING,
        **extra: str,
    ) -> T:
        """Insert a run record with optional extra columns."""
        if set(extra.keys()) != set(self.extra_columns):
            missing_or_extra = set(self.extra_columns) ^ set(extra.keys())
            raise ValueError(
                f"Invalid kwargs for insert in '{self.table}': expected extra columns {self.extra_columns}, got mismatched keys: {missing_or_extra}"
            )

        status_str = status.value if isinstance(status, RunStatus) else str(status)
        cols = ("session_id", *self.extra_columns, "status")
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        insert_sql = f"INSERT INTO {self.table} ({col_names}) VALUES ({placeholders});"
        select_sql = f"SELECT * FROM {self.table} WHERE session_id = ?;"

        values = (session_id, *(extra[col] for col in self.extra_columns), status_str)

        with self.cursor() as cursor:
            try:
                cursor.execute(insert_sql, values)
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"Run with session_id '{session_id}' already exists or failed constraints: {exc}"
                ) from exc

            cursor.execute(select_sql, (session_id,))
            row = cursor.fetchone()
            if row is None:  # pragma: no cover
                raise RuntimeError(f"Failed to read run row after insert: {session_id}")
            return self._record_from_row(row)

    def get(self, session_id: str) -> T | None:
        """Return the run record matching ``session_id``, or ``None``."""
        row = self.fetch_one(f"SELECT * FROM {self.table} WHERE session_id = ?;", (session_id,))
        return self._record_from_row(row) if row is not None else None

    def update_status(
        self,
        session_id: str,
        status: RunStatus | str,
        error_message: str | None = None,
    ) -> T | None:
        """Update status, optional completed_at timestamp, and error message for a run record."""
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

        update_sql = f"""
        UPDATE {self.table}
        SET status = ?, completed_at = ?, error_message = ?
        WHERE session_id = ?;
        """

        with self.cursor() as cursor:
            try:
                cursor.execute(update_sql, (status_str, completed_at, error_message, session_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Invalid status update constraint: {exc}") from exc

            if cursor.rowcount == 0:
                return None
            cursor.execute(f"SELECT * FROM {self.table} WHERE session_id = ?;", (session_id,))
            row = cursor.fetchone()
            return self._record_from_row(row) if row is not None else None

    def save_pause(
        self,
        session_id: str,
        checkpoint_json: str,
        error_message: str | None = None,
    ) -> T | None:
        """Persist a paused checkpoint without completing the run."""
        update_sql = f"""
        UPDATE {self.table}
        SET status = ?, completed_at = NULL, error_message = ?, checkpoint_json = ?
        WHERE session_id = ?;
        """
        with self.cursor() as cursor:
            try:
                cursor.execute(
                    update_sql,
                    (RunStatus.PAUSED.value, error_message, checkpoint_json, session_id),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Invalid status update constraint: {exc}") from exc
            if cursor.rowcount == 0:
                return None
            cursor.execute(f"SELECT * FROM {self.table} WHERE session_id = ?;", (session_id,))
            row = cursor.fetchone()
            return self._record_from_row(row) if row is not None else None

    def list(self) -> list[T]:
        """List run records ordered by ``started_at`` descending."""
        rows = self.fetch_all(f"SELECT * FROM {self.table} ORDER BY started_at DESC;")
        return [self._record_from_row(row) for row in rows]
