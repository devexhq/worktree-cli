"""Pydantic and SQLModel record models and enums for the database layer."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlmodel import Field, SQLModel


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


class BlueprintKind(StrEnum):
    """Derived catalog kind for a blueprint document."""

    TASK = "task"
    WORKFLOW = "workflow"


def _now_utc_str() -> str:
    """Return the current UTC timestamp formatted as a date-time string."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


class SandboxRecord(SQLModel, table=True):
    """Row shape for the local `sandboxes` table."""

    __tablename__: Any = "sandboxes"
    model_config = {"extra": "forbid"}

    id: str = Field(primary_key=True)
    name: str | None = Field(default=None)
    branch_name: str
    base_commit: str
    sandbox_path: Path = Field(unique=True)
    status: SandboxStatus = Field(default=SandboxStatus.ACTIVE, index=True)
    created_at: str = Field(default_factory=_now_utc_str)
    updated_at: str = Field(default_factory=_now_utc_str)

    def __init__(self, **data: Any) -> None:
        """Initialize SandboxRecord, coercing string paths to Path instances."""
        if "sandbox_path" in data and isinstance(data["sandbox_path"], str):
            data["sandbox_path"] = Path(data["sandbox_path"])
        super().__init__(**data)

    @property
    def path(self) -> Path:
        """Convenience property accessing sandbox_path as a Path."""
        return self.sandbox_path


class CatalogRecord(SQLModel, table=True):
    """Row shape for the local `catalog` table."""

    __tablename__: Any = "catalog"
    model_config = {"extra": "forbid"}

    id: int | None = Field(default=None, primary_key=True)
    sha: str = Field(unique=True, index=True)
    item_type: CatalogItemType = Field(index=True)
    name: str
    path: Path = Field(unique=True, index=True)
    checksum: str
    created_at: str = Field(default_factory=_now_utc_str)
    updated_at: str = Field(default_factory=_now_utc_str)

    def __init__(self, **data: Any) -> None:
        """Initialize CatalogRecord, coercing string paths to Path instances."""
        if "path" in data and isinstance(data["path"], str):
            data["path"] = Path(data["path"])
        super().__init__(**data)


class RunRecord(SQLModel, table=True):
    """Row shape for the local `runs` table."""

    __tablename__: Any = "runs"
    model_config = {"extra": "forbid"}

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(unique=True, index=True)
    blueprint_name: str
    kind: BlueprintKind
    branch_name: str = Field(default="")
    status: RunStatus = Field(default=RunStatus.RUNNING, index=True)
    started_at: str = Field(default_factory=_now_utc_str, index=True)
    completed_at: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    checkpoint_json: str | None = Field(default=None)


class WorkflowCostRecord(SQLModel, table=True):
    """Row shape for the local `workflow_costs` table."""

    __tablename__: Any = "workflow_costs"
    model_config = {"extra": "forbid"}

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    branch_name: str
    model_id: str
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    estimated_usd_cost: float = Field(default=0.0)
    created_at: str = Field(default_factory=_now_utc_str, index=True)
