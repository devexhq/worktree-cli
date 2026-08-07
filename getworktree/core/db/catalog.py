"""CRUD helpers for catalog index records in SQLite."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from getworktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
)
from getworktree.core.db.migrations import init_database
from getworktree.core.db.models import CatalogItemType, CatalogRecord


def _catalog_record_from_row(row: sqlite3.Row) -> CatalogRecord:
    """Map a `catalog` SQLite row to a strict `CatalogRecord`."""
    return CatalogRecord(
        id=row["id"],
        sha=row["sha"],
        item_type=CatalogItemType(row["item_type"]),
        name=row["name"],
        path=Path(row["path"]),
        checksum=row["checksum"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def upsert_catalog_item(
    sha: str,
    item_type: CatalogItemType | str,
    name: str,
    path: Path | str,
    checksum: str,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> CatalogRecord:
    """Insert a new catalog record or update `item_type`, `name`, `path`, `checksum`, and `updated_at` on sha match."""
    db_path = init_database(cwd, db_rel_path)
    str_path = str(path)
    type_str = item_type.value if isinstance(item_type, CatalogItemType) else str(item_type)
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    upsert_sql = """
    INSERT INTO catalog (sha, item_type, name, path, checksum, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        sha = excluded.sha,
        item_type = excluded.item_type,
        name = excluded.name,
        checksum = excluded.checksum,
        updated_at = excluded.updated_at;
    """
    select_sql = "SELECT * FROM catalog WHERE path = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                upsert_sql,
                (sha, type_str, name, str_path, checksum, now_utc, now_utc),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Invalid catalog item constraint violation: {exc}") from exc

        cursor.execute(select_sql, (str_path,))
        row = cursor.fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError(f"Failed to read catalog row after upsert: {sha}")
        return _catalog_record_from_row(row)


def list_catalog_items(
    item_type: CatalogItemType | str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> list[CatalogRecord]:
    """List catalog records, optionally filtered by ``item_type``."""
    db_path = init_database(cwd, db_rel_path)

    if item_type is None:
        query_sql = "SELECT * FROM catalog ORDER BY id ASC;"
        params: tuple[object, ...] = ()
    else:
        type_str = item_type.value if isinstance(item_type, CatalogItemType) else str(item_type)
        query_sql = "SELECT * FROM catalog WHERE item_type = ? ORDER BY id ASC;"
        params = (type_str,)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
        return [_catalog_record_from_row(row) for row in rows]


def get_catalog_item_by_sha(
    sha: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> CatalogRecord | None:
    """Return the catalog record matching ``sha``, or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM catalog WHERE sha = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (sha,))
        row = cursor.fetchone()
        return _catalog_record_from_row(row) if row is not None else None


def get_catalog_item_by_name(
    name: str,
    item_type: CatalogItemType | str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> CatalogRecord | None:
    """Return the catalog record matching ``name`` (and optional ``item_type``), or ``None``."""
    db_path = init_database(cwd, db_rel_path)

    if item_type is None:
        select_sql = "SELECT * FROM catalog WHERE name = ?;"
        params: tuple[object, ...] = (name,)
    else:
        type_str = item_type.value if isinstance(item_type, CatalogItemType) else str(item_type)
        select_sql = "SELECT * FROM catalog WHERE name = ? AND item_type = ?;"
        params = (name, type_str)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, params)
        row = cursor.fetchone()
        return _catalog_record_from_row(row) if row is not None else None


def delete_catalog_item(sha: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH) -> bool:
    """Delete a catalog record by ``sha``. Returns ``True`` if a row was deleted."""
    db_path = init_database(cwd, db_rel_path)
    delete_sql = "DELETE FROM catalog WHERE sha = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(delete_sql, (sha,))
        return cursor.rowcount > 0
