"""CRUD helpers for run execution tracking in SQLite using RunsDb repository."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from worktree.core.db.base import DbBase
from worktree.core.db.models import BlueprintKind, RunRecord, RunStatus


class RunsDb(DbBase):
    """Repository managing unified blueprint execution tracking CRUD operations in SQLite."""

    def _record_from_row(self, row: sqlite3.Row) -> RunRecord:
        """Map a SQLite row to a RunRecord model."""
        return RunRecord(
            id=row["id"],
            session_id=row["session_id"],
            blueprint_name=row["blueprint_name"],
            kind=BlueprintKind(row["kind"]),
            branch_name=row["branch_name"] if "branch_name" in row.keys() and row["branch_name"] is not None else "",
            status=RunStatus(row["status"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            checkpoint_json=row["checkpoint_json"] if "checkpoint_json" in row.keys() else None,
        )

    def create(
        self,
        session_id: str,
        blueprint_name: str,
        kind: BlueprintKind | str,
        branch_name: str = "",
        status: RunStatus | str = RunStatus.RUNNING,
    ) -> RunRecord:
        """Insert a new run record and return the created model."""
        kind_str = kind.value if isinstance(kind, BlueprintKind) else str(kind)
        status_str = status.value if isinstance(status, RunStatus) else str(status)

        insert_sql = """
        INSERT INTO runs (session_id, blueprint_name, kind, branch_name, status)
        VALUES (?, ?, ?, ?, ?);
        """
        select_sql = "SELECT * FROM runs WHERE session_id = ?;"
        values = (session_id, blueprint_name, kind_str, branch_name, status_str)

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

    insert = create

    def get(self, session_id: str) -> RunRecord | None:
        """Return the run record matching ``session_id``, or None."""
        row = self.fetch_one("SELECT * FROM runs WHERE session_id = ?;", (session_id,))
        return self._record_from_row(row) if row is not None else None

    def update_status(
        self,
        session_id: str,
        status: RunStatus | str,
        error_message: str | None = None,
        checkpoint_json: str | None = None,
        completed_at: str | None = None,
    ) -> RunRecord | None:
        """Update status, optional timestamps, error message, and checkpoint JSON."""
        status_enum = (
            RunStatus(status) if isinstance(status, str) and status in RunStatus._value2member_map_ else status
        )
        status_str = status_enum.value if isinstance(status_enum, RunStatus) else str(status)

        if completed_at is None and status_str in (
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        ):
            completed_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        with self.cursor() as cursor:
            try:
                if checkpoint_json is not None:
                    cursor.execute(
                        """
                        UPDATE runs
                        SET status = ?, completed_at = ?, error_message = ?, checkpoint_json = ?
                        WHERE session_id = ?;
                        """,
                        (status_str, completed_at, error_message, checkpoint_json, session_id),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE runs
                        SET status = ?, completed_at = ?, error_message = ?
                        WHERE session_id = ?;
                        """,
                        (status_str, completed_at, error_message, session_id),
                    )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Invalid status update constraint: {exc}") from exc

            if cursor.rowcount == 0:
                return None
            cursor.execute("SELECT * FROM runs WHERE session_id = ?;", (session_id,))
            row = cursor.fetchone()
            return self._record_from_row(row) if row is not None else None

    def save_pause(
        self,
        session_id: str,
        checkpoint_json: str,
        error_message: str | None = None,
    ) -> RunRecord | None:
        """Persist a paused checkpoint without completing the run."""
        return self.update_status(
            session_id=session_id,
            status=RunStatus.PAUSED,
            error_message=error_message,
            checkpoint_json=checkpoint_json,
            completed_at=None,
        )

    def list(
        self,
        limit: int | None = None,
        status: RunStatus | str | None = None,
        kind: BlueprintKind | str | None = None,
    ) -> list[RunRecord]:
        """List run records ordered by ``started_at DESC, id DESC`` with optional filters."""
        query = "SELECT * FROM runs"
        conditions: list[str] = []
        params: list[Any] = []

        if status is not None:
            status_str = status.value if isinstance(status, RunStatus) else str(status)
            conditions.append("status = ?")
            params.append(status_str)

        if kind is not None:
            kind_str = kind.value if isinstance(kind, BlueprintKind) else str(kind)
            conditions.append("kind = ?")
            params.append(kind_str)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY started_at DESC, id DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = self.fetch_all(query + ";", tuple(params))
        return [self._record_from_row(row) for row in rows]

    def get_latest_paused(self) -> RunRecord | None:
        """Return the most recent run where status == RunStatus.PAUSED, or None."""
        row = self.fetch_one(
            "SELECT * FROM runs WHERE status = ? ORDER BY started_at DESC, id DESC LIMIT 1;",
            (RunStatus.PAUSED.value,),
        )
        return self._record_from_row(row) if row is not None else None
