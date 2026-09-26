"""Result types for the blueprint execution engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from worktree.common.models import BaseResult
from worktree.core.db import RunRecord
from worktree.core.runtime.models import FailurePrompter, RunObserver
from worktree.core.step.models import StepResult


class EngineResumeStatus(StrEnum):
    """Classified outcomes for ``ResumableRun.load`` / ``Engine.resume``."""

    OK = "ok"
    NOT_FOUND = "not_found"
    WRONG_STATUS = "wrong_status"
    MISSING_SANDBOX = "missing_sandbox"
    CORRUPT_CHECKPOINT = "corrupt_checkpoint"
    MISSING_SNAPSHOT = "missing_snapshot"
    FAILED = "failed"


@dataclass(frozen=True)
class RunRequest:
    """Caller options for ``Engine.run``."""

    inputs: dict[str, str | int | bool] | None = None
    cli_args: list[str] | None = None
    use_sandbox: bool | None = None
    keep: bool = False
    agent: str | None = None
    session_id: str | None = None
    observer: RunObserver | None = None
    failure_prompter: FailurePrompter | None = None
    no_tty: bool = False
    auto_apply: bool = False


class DefinitionRef(BaseModel):
    """One snapshotted catalog item's resolved reference, content hash, and resolution time."""

    model_config = {"extra": "forbid", "strict": True}

    ref: str
    sha: str
    resolved_at: str


class DefinitionsManifest(BaseModel):
    """Manifest of the blueprint and uses:-referenced steps snapshotted for a run's session."""

    model_config = {"extra": "forbid", "strict": True}

    blueprint: DefinitionRef
    steps: list[DefinitionRef] = Field(default_factory=list)


class SessionRunPayload(BaseModel):
    """Persisted execution results and telemetry for a session."""

    model_config = {"extra": "forbid", "strict": True}

    version: int = 1
    session_id: str
    name: str
    status: str
    started_at: str
    completed_at: str | None = None
    error_message: str | None = None
    step_results: list[StepResult] = Field(default_factory=list)
    definitions: DefinitionsManifest | None = None


class ReconciliationResult(BaseResult):
    """Result of reconciling stale running sessions."""

    reconciled: list[RunRecord] = Field(default_factory=list)
    warning: str | None = None
