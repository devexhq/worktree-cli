from __future__ import annotations

from typing import Any

from sqlmodel import SQLModel

from worktree.core.blueprint import BlueprintDefinition
from worktree.core.catalog.models import CatalogItem
from worktree.core.db import (
    BaseRepository,
    CatalogItemType,
    CatalogRecord,
    CatalogRepository,
    RunRecord,
    RunsRepository,
    RunStatus,
    SandboxesRepository,
    SandboxRecord,
    SandboxStatus,
)
from worktree.core.runtime import RunCheckpoint

from .make import make_checkpoint


class BaseFactory[ModelT: SQLModel, RepoT: BaseRepository]:
    """Base factory supporting static pure builds and repo-bound persistence."""

    _model: type[ModelT]

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        """Override in subclasses to provide test defaults."""
        return {}

    @classmethod
    def build(cls, **kwargs: Any) -> ModelT:
        """Pure, stateless factory to generate an in-memory model with defaults."""
        fields = {**cls.defaults(), **kwargs}
        return cls._model.model_validate(fields)

    @classmethod
    def create(cls, repo: RepoT, **kwargs: Any) -> ModelT:
        """Persist a factory instance using the bound repository session."""
        instance = cls.build(**kwargs)
        with repo.session() as session:
            session.add(instance)
            session.commit()
            session.refresh(instance)
        return instance


class RunFactory:
    """Create and query persisted run records for tests."""

    def __init__(self, repository: RunsRepository) -> None:
        self._repository = repository

    def create(
        self,
        *,
        session_id: str = "sample-run-1",
        blueprint_name: str = "sample-blueprint",
        blueprint_key: str = "sample-blueprint",
        status: RunStatus = RunStatus.COMPLETED,
        branch_name: str = "main",
        pid: int | None = None,
        started_at: str = "2026-08-19 01:00:00",
        completed_at: str | None = "2026-08-19 01:00:15",
        error_message: str | None = None,
        checkpoint_json: str | None = None,
    ) -> RunRecord:
        """Persist a run record with deterministic defaults for tests."""
        record = RunRecord(
            session_id=session_id,
            blueprint_name=blueprint_name,
            blueprint_key=blueprint_key,
            status=status,
            branch_name=branch_name,
            pid=pid,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
            checkpoint_json=checkpoint_json,
        )
        with self._repository.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def create_paused(
        self,
        *,
        session_id: str,
        blueprint: CatalogItem[BlueprintDefinition],
        checkpoint: RunCheckpoint | None = None,
        branch_name: str = "wt/resume",
    ) -> RunRecord:
        """Persist a paused run through the repository's pause transition."""
        self.create(
            session_id=session_id,
            blueprint_name=blueprint.definition.name,
            blueprint_key=blueprint.key,
            status=RunStatus.RUNNING,
            branch_name=branch_name,
            completed_at=None,
        )
        paused = self._repository.save_pause(
            session_id,
            (checkpoint or make_checkpoint()).model_dump_json(),
            "paused",
        )
        if paused is None:
            raise RuntimeError(f"Failed to pause seeded run '{session_id}'.")
        return paused

    def get(self, session_id: str) -> RunRecord | None:
        """Return the run matching a session ID."""
        return self._repository.get(session_id)

    def list(
        self,
        *,
        limit: int | None = None,
        status: RunStatus | str | None = None,
    ) -> list[RunRecord]:
        """Return persisted runs in repository order with optional filters."""
        return self._repository.list(limit=limit, status=status)


class CatalogFactory(BaseFactory[CatalogRecord, CatalogRepository]):
    _model = CatalogRecord

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return {
            "sha": "sample-workflow-sha-1",
            "item_type": CatalogItemType.BLUEPRINT,
            "name": "sample-workflow-1",
            "path": ".worktree/catalog/workflows/sample-workflow-1.yaml",
            "checksum": "sample-workflow-checksum-1",
            "created_at": "2026-08-19 01:00:00",
            "updated_at": "2026-08-19 01:00:15",
        }


class SandboxFactory(BaseFactory[SandboxRecord, SandboxesRepository]):
    _model = SandboxRecord

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return {
            "id": "sbx_1",
            "name": "sandbox-1",
            "branch_name": "main",
            "base_commit": "979e2fc",
            "sandbox_path": ".worktree/sandboxes/sample-sandbox",
            "status": SandboxStatus.ACTIVE,
            "created_at": "2026-08-19 01:00:00",
            "updated_at": "2026-08-19 01:00:15",
        }
