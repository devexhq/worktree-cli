"""CRUD helpers for sandbox metadata in SQLite using SandboxesDb repository."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from getworktree.core.db.base import DbBase
from getworktree.core.db.models import SandboxRecord, SandboxStatus


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


class SandboxesDb(DbBase):
    """Repository managing sandbox metadata CRUD operations in SQLite."""

    def insert(
        self,
        id: str,
        branch_name: str,
        base_commit: str,
        sandbox_path: Path,
        name: str | None = None,
    ) -> SandboxRecord:
        """Insert a sandbox metadata row with status ``active``.

        Returns:
            The inserted `SandboxRecord`, including DB-assigned timestamps.

        Raises:
            ValueError: If a row with the same ``id`` already exists.
        """
        insert_sql = """
        INSERT INTO sandboxes (
            id, name, branch_name, base_commit, sandbox_path, status
        ) VALUES (?, ?, ?, ?, ?, ?);
        """
        select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

        with self.cursor() as cursor:
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

    def get(self, id: str) -> SandboxRecord | None:
        """Return the sandbox row for ``id``, or ``None`` when missing."""
        row = self.fetch_one("SELECT * FROM sandboxes WHERE id = ?;", (id,))
        return _sandbox_record_from_row(row) if row is not None else None

    def list(self, status: SandboxStatus | None = None) -> list[SandboxRecord]:
        """List sandbox rows ordered by ``created_at`` descending.

        When ``status`` is set, only rows with that status are returned.
        """
        if status is None:
            rows = self.fetch_all("SELECT * FROM sandboxes ORDER BY created_at DESC;")
        else:
            rows = self.fetch_all(
                "SELECT * FROM sandboxes WHERE status = ? ORDER BY created_at DESC;",
                (status.value,),
            )
        return [_sandbox_record_from_row(row) for row in rows]

    def update_status(self, id: str, status: SandboxStatus) -> SandboxRecord | None:
        """Update sandbox status and ``updated_at``; return the row or ``None``."""
        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        update_sql = """
        UPDATE sandboxes
        SET status = ?, updated_at = ?
        WHERE id = ?;
        """
        if self.execute(update_sql, (status.value, now_utc, id)) == 0:
            return None
        return self.get(id)

    def delete(self, id: str) -> bool:
        """Hard-delete a sandbox metadata row. Returns whether a row was removed."""
        return self.execute("DELETE FROM sandboxes WHERE id = ?;", (id,)) > 0
