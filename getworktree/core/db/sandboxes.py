"""CRUD helpers for sandbox metadata in SQLite."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from getworktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
)
from getworktree.core.db.migrations import init_database
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


def insert_sandbox(
    id: str,
    branch_name: str,
    base_commit: str,
    sandbox_path: Path,
    name: str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> SandboxRecord:
    """Insert a sandbox metadata row with status ``active``.

    Returns:
        The inserted `SandboxRecord`, including DB-assigned timestamps.

    Raises:
        ValueError: If a row with the same ``id`` already exists.
    """
    db_path = init_database(cwd, db_rel_path)
    insert_sql = """
    INSERT INTO sandboxes (
        id, name, branch_name, base_commit, sandbox_path, status
    ) VALUES (?, ?, ?, ?, ?, ?);
    """
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
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


def get_sandbox(
    id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> SandboxRecord | None:
    """Return the sandbox row for ``id``, or ``None`` when missing."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        return _sandbox_record_from_row(row) if row is not None else None


def list_sandboxes(
    status: SandboxStatus | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> list[SandboxRecord]:
    """List sandbox rows ordered by ``created_at`` descending.

    When ``status`` is set, only rows with that status are returned.
    """
    db_path = init_database(cwd, db_rel_path)

    if status is None:
        query_sql = "SELECT * FROM sandboxes ORDER BY created_at DESC;"
        params: tuple[object, ...] = ()
    else:
        query_sql = "SELECT * FROM sandboxes WHERE status = ? ORDER BY created_at DESC;"
        params = (status.value,)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
        return [_sandbox_record_from_row(row) for row in rows]


def update_sandbox_status(
    id: str,
    status: SandboxStatus,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> SandboxRecord | None:
    """Update sandbox status and ``updated_at``; return the row or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    update_sql = """
    UPDATE sandboxes
    SET status = ?, updated_at = ?
    WHERE id = ?;
    """
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(update_sql, (status.value, now_utc, id))
        if cursor.rowcount == 0:
            return None
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        return _sandbox_record_from_row(row) if row is not None else None


def delete_sandbox_row(
    id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> bool:
    """Hard-delete a sandbox metadata row. Returns whether a row was removed."""
    db_path = init_database(cwd, db_rel_path)
    delete_sql = "DELETE FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(delete_sql, (id,))
        return cursor.rowcount > 0
