from __future__ import annotations

from typing import Any

from sqlmodel import SQLModel

from worktree.core.db import (
    BaseRepository,
    BlueprintKind,
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


class RunFactory(BaseFactory[RunRecord, RunsRepository]):
    _model = RunRecord

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return {
            "session_id": "sample-run-1",
            "blueprint_name": "sample-task-1",
            "kind": BlueprintKind.TASK,
            "status": RunStatus.COMPLETED,
            "branch_name": "main",
            "pid": None,
            "started_at": "2026-08-19 01:00:00",
            "completed_at": "2026-08-19 01:00:15",
            "error_message": None,
            "checkpoint_json": None,
        }


class CatalogFactory(BaseFactory[CatalogRecord, CatalogRepository]):
    _model = CatalogRecord

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return {
            "sha": "sample-workflow-sha-1",
            "item_type": CatalogItemType.WORKFLOW,
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
