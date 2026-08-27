"""Repository managing catalog index records CRUD operations using SQLModel."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from worktree.core.db.models import CatalogItemType, CatalogRecord
from worktree.core.db.repositories.base import BaseRepository


def _coerce_item_type(item_type: CatalogItemType | str) -> CatalogItemType:
    """Coerce string or CatalogItemType into a CatalogItemType enum, raising ValueError on failure."""
    if isinstance(item_type, CatalogItemType):
        return item_type
    try:
        return CatalogItemType(str(item_type))
    except ValueError as exc:
        raise ValueError(f"Invalid catalog item constraint violation: {exc}") from exc


class CatalogRepository(BaseRepository):
    """Repository managing catalog index records CRUD operations using SQLModel."""

    def upsert(
        self,
        sha: str,
        item_type: CatalogItemType | str,
        name: str,
        path: Path | str,
        checksum: str,
    ) -> CatalogRecord:
        """Insert a new catalog record or update fields on ``path`` match.

        If a record with the same ``path`` already exists, its ``sha``,
        ``item_type``, ``name``, ``checksum``, and ``updated_at`` are updated
        in-place and the existing ``id`` / ``created_at`` are preserved.

        Returns:
            The committed `CatalogRecord`.

        Raises:
            ValueError: If the ``item_type`` is not a valid `CatalogItemType` value.
        """
        coerced_path = Path(str(path))
        type_enum = _coerce_item_type(item_type)

        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        with self.session() as session:
            statement = select(CatalogRecord).where(CatalogRecord.path == coerced_path)
            existing = session.exec(statement).first()

            if existing is not None:
                existing.sha = sha
                existing.item_type = type_enum
                existing.name = name
                existing.checksum = checksum
                existing.updated_at = now_utc
                record = existing
            else:
                record = CatalogRecord(
                    sha=sha,
                    item_type=type_enum,
                    name=name,
                    path=coerced_path,
                    checksum=checksum,
                    created_at=now_utc,
                    updated_at=now_utc,
                )

            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(f"Invalid catalog item constraint violation: {exc}") from exc

            session.refresh(record)
            return record

    def get_by_path(self, path: Path | str) -> CatalogRecord | None:
        """Fetch a catalog record by its relative or stored path."""
        coerced_path = Path(str(path))
        with self.session() as session:
            statement = select(CatalogRecord).where(CatalogRecord.path == coerced_path)
            return session.exec(statement).first()

    def list(
        self,
        item_type: CatalogItemType | str | None = None,
    ) -> list[CatalogRecord]:
        """List catalog records, optionally filtered by ``item_type``."""
        with self.session() as session:
            statement = select(CatalogRecord)
            if item_type is not None:
                type_enum = _coerce_item_type(item_type)
                statement = statement.where(CatalogRecord.item_type == type_enum)
            statement = statement.order_by(col(CatalogRecord.id).asc())
            return list(session.exec(statement).all())

    def get_by_sha(self, sha: str) -> CatalogRecord | None:
        """Return the catalog record matching ``sha``, or ``None``."""
        with self.session() as session:
            statement = select(CatalogRecord).where(CatalogRecord.sha == sha)
            return session.exec(statement).first()

    def get_by_name(
        self,
        name: str,
        item_type: CatalogItemType | str | None = None,
    ) -> CatalogRecord | None:
        """Return the catalog record matching ``name`` (and optional ``item_type``), or ``None``."""
        with self.session() as session:
            statement = select(CatalogRecord).where(CatalogRecord.name == name)
            if item_type is not None:
                type_enum = _coerce_item_type(item_type)
                statement = statement.where(CatalogRecord.item_type == type_enum)
            return session.exec(statement).first()

    def list_by_name(
        self,
        name: str,
        item_type: CatalogItemType | str | None = None,
    ) -> list[CatalogRecord]:
        """Return all catalog records matching ``name`` (and optional ``item_type``), ordered by path ASC."""
        with self.session() as session:
            statement = select(CatalogRecord).where(CatalogRecord.name == name)
            if item_type is not None:
                type_enum = _coerce_item_type(item_type)
                statement = statement.where(CatalogRecord.item_type == type_enum)
            statement = statement.order_by(col(CatalogRecord.path).asc())
            return list(session.exec(statement).all())

    def delete(self, sha: str) -> bool:
        """Delete a catalog record by ``sha``. Returns ``True`` if a row was deleted."""
        with self.session() as session:
            statement = select(CatalogRecord).where(CatalogRecord.sha == sha)
            record = session.exec(statement).first()
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True
