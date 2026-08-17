"""Pydantic record models and enums for the database layer."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class SandboxStatus(StrEnum):
    """Lifecycle status for a persisted sandbox metadata row."""

    ACTIVE = "active"
    MERGED = "merged"
    CLEANED = "cleaned"
    CONFLICT = "conflict"


class CatalogItemType(StrEnum):
    """Supported catalog item classification types."""

    WORKFLOW = "workflow"
    TASK = "task"
    STEP = "step"


class RunStatus(StrEnum):
    """Lifecycle status for workflow and task execution sessions."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class SandboxRecord(BaseModel):
    """Row shape for the local `sandboxes` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: str
    name: str | None = None
    branch_name: str
    base_commit: str
    sandbox_path: Path
    status: SandboxStatus
    created_at: str
    updated_at: str


class CatalogRecord(BaseModel):
    """Row shape for the local `catalog` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: int
    sha: str
    item_type: CatalogItemType
    name: str
    path: Path
    checksum: str
    created_at: str
    updated_at: str


class WorkflowRunRecord(BaseModel):
    """Row shape for the local `workflows` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: int
    session_id: str
    workflow_name: str
    branch_name: str
    status: RunStatus
    started_at: str
    completed_at: str | None = None
    error_message: str | None = None
    checkpoint_json: str | None = None


class TaskRunRecord(BaseModel):
    """Row shape for the local `tasks` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: int
    session_id: str
    task_name: str
    status: RunStatus
    started_at: str
    completed_at: str | None = None
    error_message: str | None = None
    checkpoint_json: str | None = None
