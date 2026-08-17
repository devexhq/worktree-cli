from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from worktree.core.db.base import DbBase
from worktree.core.db.models import CatalogItemType, CatalogRecord


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


class CatalogDb(DbBase):
    """Repository managing catalog index records CRUD operations in SQLite."""

    def upsert(
        self,
        sha: str,
        item_type: CatalogItemType | str,
        name: str,
        path: Path | str,
        checksum: str,
    ) -> CatalogRecord:
        """Insert a new catalog record or update ``item_type``, ``name``, ``path``, ``checksum``, and ``updated_at`` on sha/path match."""
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

        with self.cursor() as cursor:
            try:
                cursor.execute(
                    upsert_sql,
                    (sha, type_str, name, str_path, checksum, now_utc, now_utc),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Invalid catalog item constraint violation: {exc}") from exc

            cursor.execute("SELECT * FROM catalog WHERE path = ?;", (str_path,))
            row = cursor.fetchone()
            if row is None:  # pragma: no cover
                raise RuntimeError(f"Failed to read catalog row after upsert: {sha}")
            return _catalog_record_from_row(row)

    def list(
        self,
        item_type: CatalogItemType | str | None = None,
    ) -> list[CatalogRecord]:
        """List catalog records, optionally filtered by ``item_type``."""
        if item_type is None:
            rows = self.fetch_all("SELECT * FROM catalog ORDER BY id ASC;")
        else:
            type_str = item_type.value if isinstance(item_type, CatalogItemType) else str(item_type)
            rows = self.fetch_all("SELECT * FROM catalog WHERE item_type = ? ORDER BY id ASC;", (type_str,))
        return [_catalog_record_from_row(row) for row in rows]

    def get_by_sha(self, sha: str) -> CatalogRecord | None:
        """Return the catalog record matching ``sha``, or ``None``."""
        row = self.fetch_one("SELECT * FROM catalog WHERE sha = ?;", (sha,))
        return _catalog_record_from_row(row) if row is not None else None

    def get_by_name(
        self,
        name: str,
        item_type: CatalogItemType | str | None = None,
    ) -> CatalogRecord | None:
        """Return the catalog record matching ``name`` (and optional ``item_type``), or ``None``."""
        if item_type is None:
            row = self.fetch_one("SELECT * FROM catalog WHERE name = ?;", (name,))
        else:
            type_str = item_type.value if isinstance(item_type, CatalogItemType) else str(item_type)
            row = self.fetch_one("SELECT * FROM catalog WHERE name = ? AND item_type = ?;", (name, type_str))
        return _catalog_record_from_row(row) if row is not None else None

    def list_by_name(
        self,
        name: str,
        item_type: CatalogItemType | str | None = None,
    ) -> list[CatalogRecord]:
        """Return all catalog records matching ``name`` (and optional ``item_type``), ordered by path ASC."""
        if item_type is None:
            rows = self.fetch_all("SELECT * FROM catalog WHERE name = ? ORDER BY path ASC;", (name,))
        else:
            type_str = item_type.value if isinstance(item_type, CatalogItemType) else str(item_type)
            rows = self.fetch_all(
                "SELECT * FROM catalog WHERE name = ? AND item_type = ? ORDER BY path ASC;",
                (name, type_str),
            )
        return [_catalog_record_from_row(row) for row in rows]

    def delete(self, sha: str) -> bool:
        """Delete a catalog record by ``sha``. Returns ``True`` if a row was deleted."""
        return self.execute("DELETE FROM catalog WHERE sha = ?;", (sha,)) > 0
