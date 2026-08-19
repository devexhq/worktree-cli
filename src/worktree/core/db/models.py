"""Pydantic and SQLModel record models and enums for the database layer."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import String, TypeDecorator
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


class PathType(TypeDecorator[Path]):
    """SQLAlchemy type for coercing Path objects to strings and back."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Path | str | None, dialect: Any) -> str | None:
        """Coerce incoming Path or str object to string for SQLite storage."""
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: str | None, dialect: Any) -> Path | None:
        """Coerce retrieved database string value back into a Path instance."""
        if value is None:
            return None
        return Path(value)


class SandboxRecord(SQLModel, table=True):
    """Row shape for the local `sandboxes` table."""

    __tablename__: Any = "sandboxes"
    model_config = {"extra": "forbid"}

    id: str = Field(primary_key=True)
    name: str | None = Field(default=None)
    branch_name: str
    base_commit: str
    sandbox_path: Path = Field(sa_type=PathType, unique=True)
    status: SandboxStatus = Field(default=SandboxStatus.ACTIVE, sa_type=String, index=True)
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
    item_type: CatalogItemType = Field(sa_type=String, index=True)
    name: str
    path: Path = Field(sa_type=PathType, unique=True, index=True)
    checksum: str
    created_at: str = Field(default_factory=_now_utc_str)
    updated_at: str = Field(default_factory=_now_utc_str)

    def __init__(self, **data: Any) -> None:
        """Initialize CatalogRecord, coercing string paths to Path instances."""
        if "path" in data and isinstance(data["path"], str):
            data["path"] = Path(data["path"])
        super().__init__(**data)


class BlueprintKindType(TypeDecorator[BlueprintKind]):
    """SQLAlchemy type for coercing BlueprintKind enums to strings and back."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: BlueprintKind | str | None, dialect: Any) -> str | None:
        """Coerce incoming BlueprintKind or str to string for SQLite storage."""
        if value is None:
            return None
        return value.value if isinstance(value, BlueprintKind) else str(value)

    def process_result_value(self, value: str | None, dialect: Any) -> BlueprintKind | None:
        """Coerce retrieved database string value back into a BlueprintKind instance."""
        if value is None:
            return None
        return BlueprintKind(value)


class RunStatusType(TypeDecorator[RunStatus]):
    """SQLAlchemy type for coercing RunStatus enums to strings and back."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: RunStatus | str | None, dialect: Any) -> str | None:
        """Coerce incoming RunStatus or str to string for SQLite storage."""
        if value is None:
            return None
        return value.value if isinstance(value, RunStatus) else str(value)

    def process_result_value(self, value: str | None, dialect: Any) -> RunStatus | None:
        """Coerce retrieved database string value back into a RunStatus instance."""
        if value is None:
            return None
        return RunStatus(value)


class RunRecord(SQLModel, table=True):
    """Row shape for the local `runs` table."""

    __tablename__: Any = "runs"
    model_config = {"extra": "forbid"}

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(unique=True, index=True)
    blueprint_name: str
    kind: BlueprintKind = Field(sa_type=BlueprintKindType)
    branch_name: str = Field(default="")
    status: RunStatus = Field(default=RunStatus.RUNNING, sa_type=RunStatusType, index=True)
    started_at: str = Field(default_factory=_now_utc_str, index=True)
    completed_at: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    checkpoint_json: str | None = Field(default=None)

    def __init__(self, **data: Any) -> None:
        """Initialize RunRecord, coercing string enums to Enum instances."""
        if "kind" in data and isinstance(data["kind"], str):
            data["kind"] = BlueprintKind(data["kind"])
        if "status" in data and isinstance(data["status"], str):
            data["status"] = RunStatus(data["status"])
        super().__init__(**data)


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
