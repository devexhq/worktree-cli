"""Repository managing sandbox metadata CRUD operations using SQLModel."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from worktree.core.db.models import SandboxRecord, SandboxStatus
from worktree.core.db.repositories.base import BaseRepository


class SandboxesRepository(BaseRepository):
    """Repository managing sandbox metadata CRUD operations using SQLModel."""

    def insert(
        self,
        id: str,
        branch_name: str,
        base_commit: str,
        sandbox_path: Path | str,
        name: str | None = None,
    ) -> SandboxRecord:
        """Insert a sandbox metadata row with status ``active``.

        Returns:
            The inserted `SandboxRecord`, including DB-assigned timestamps.

        Raises:
            ValueError: If a row with the same ``id`` already exists.
        """
        record = SandboxRecord(
            id=id,
            name=name,
            branch_name=branch_name,
            base_commit=base_commit,
            sandbox_path=Path(str(sandbox_path)),
            status=SandboxStatus.ACTIVE,
        )

        with self.session() as session:
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(f"Sandbox with id '{id}' already exists") from exc
            session.refresh(record)
            return record

    def get(self, id: str) -> SandboxRecord | None:
        """Return the sandbox row for ``id``, or ``None`` when missing."""
        with self.session() as session:
            statement = select(SandboxRecord).where(SandboxRecord.id == id)
            return session.exec(statement).first()

    def list(self, status: SandboxStatus | None = None) -> list[SandboxRecord]:
        """List sandbox rows ordered by ``created_at`` descending.

        When ``status`` is set, only rows with that status are returned.
        """
        with self.session() as session:
            statement = select(SandboxRecord)
            if status is not None:
                statement = statement.where(SandboxRecord.status == status)
            statement = statement.order_by(col(SandboxRecord.created_at).desc())
            return list(session.exec(statement).all())

    def update_status(self, id: str, status: SandboxStatus) -> SandboxRecord | None:
        """Update sandbox status and ``updated_at``; return the row or ``None``."""
        with self.session() as session:
            statement = select(SandboxRecord).where(SandboxRecord.id == id)
            record = session.exec(statement).first()
            if record is None:
                return None

            record.status = status
            record.updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(f"Invalid status update constraint: {exc}") from exc

            session.refresh(record)
            return record

    def delete(self, id: str) -> bool:
        """Hard-delete a sandbox metadata row. Returns whether a row was removed."""
        with self.session() as session:
            statement = select(SandboxRecord).where(SandboxRecord.id == id)
            record = session.exec(statement).first()
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True
