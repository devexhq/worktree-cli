"""Repository managing unified blueprint execution tracking CRUD operations using SQLModel."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from worktree.core.db.models import BlueprintKind, RunRecord, RunStatus
from worktree.core.db.repositories.base import BaseRepository


def _coerce_status(status: RunStatus | str | None) -> RunStatus | str | None:
    """Coerce status string to RunStatus enum if valid member, else return as-is."""
    if status is None:
        return None
    return RunStatus(status) if isinstance(status, str) and status in RunStatus._value2member_map_ else status


def _coerce_kind(kind: BlueprintKind | str | None) -> BlueprintKind | str | None:
    """Coerce kind string to BlueprintKind enum if valid member, else return as-is."""
    if kind is None:
        return None
    return BlueprintKind(kind) if isinstance(kind, str) and kind in BlueprintKind._value2member_map_ else kind


class RunsRepository(BaseRepository):
    """Repository managing unified blueprint execution tracking CRUD operations using SQLModel."""

    def create(
        self,
        session_id: str,
        blueprint_name: str,
        kind: BlueprintKind | str,
        branch_name: str = "",
        status: RunStatus | str = RunStatus.RUNNING,
    ) -> RunRecord:
        """Insert a new run record and return the committed instance."""
        kind_enum = BlueprintKind(kind) if isinstance(kind, str) else kind
        status_enum = RunStatus(status) if isinstance(status, str) else status

        record = RunRecord(
            session_id=session_id,
            blueprint_name=blueprint_name,
            kind=kind_enum,
            branch_name=branch_name,
            status=status_enum,
        )

        with self.session() as session:
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(
                    f"Run with session_id '{session_id}' already exists or failed constraints: {exc}"
                ) from exc
            session.refresh(record)
            return record

    def get(self, session_id: str) -> RunRecord | None:
        """Return the run record matching session_id, or None."""
        with self.session() as session:
            statement = select(RunRecord).where(RunRecord.session_id == session_id)
            return session.exec(statement).first()

    def update_status(
        self,
        session_id: str,
        status: RunStatus | str,
        error_message: str | None = None,
        checkpoint_json: str | None = None,
        completed_at: str | None = None,
    ) -> RunRecord | None:
        """Update status, optional timestamps, error message, and checkpoint JSON."""
        status_enum = _coerce_status(status)
        if not isinstance(status_enum, RunStatus):
            raise ValueError(f"Invalid status constraint: {status}")

        if completed_at is None and status_enum in (
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        ):
            completed_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        with self.session() as session:
            statement = select(RunRecord).where(RunRecord.session_id == session_id)
            record = session.exec(statement).first()
            if record is None:
                return None

            record.status = status_enum
            record.completed_at = completed_at
            record.error_message = error_message
            if checkpoint_json is not None:
                record.checkpoint_json = checkpoint_json

            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(f"Invalid status update constraint: {exc}") from exc

            session.refresh(record)
            return record

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
        """List run records ordered by started_at DESC, id DESC with optional filters."""
        with self.session() as session:
            statement = select(RunRecord)

            status_enum = _coerce_status(status)
            if status_enum is not None:
                statement = statement.where(RunRecord.status == status_enum)

            kind_enum = _coerce_kind(kind)
            if kind_enum is not None:
                statement = statement.where(RunRecord.kind == kind_enum)

            statement = statement.order_by(col(RunRecord.started_at).desc(), col(RunRecord.id).desc())

            if limit is not None:
                statement = statement.limit(limit)

            return list(session.exec(statement).all())

    def get_latest_paused(self) -> RunRecord | None:
        """Return the most recent run where status == RunStatus.PAUSED, or None."""
        with self.session() as session:
            statement = (
                select(RunRecord)
                .where(RunRecord.status == RunStatus.PAUSED)
                .order_by(col(RunRecord.started_at).desc(), col(RunRecord.id).desc())
                .limit(1)
            )
            return session.exec(statement).first()
