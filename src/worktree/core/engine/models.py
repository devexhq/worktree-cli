"""Result types for the blueprint execution engine."""

from dataclasses import dataclass
from enum import StrEnum

from worktree.core.db import TasksDb, WorkflowsDb
from worktree.core.runtime import RunCheckpoint
from worktree.core.step import StepDefinition


class EngineResumeStatus(StrEnum):
    """Classified cannot-start outcomes for ``Engine.resume``."""

    NOT_FOUND = "not_found"
    WRONG_STATUS = "wrong_status"
    MISSING_SANDBOX = "missing_sandbox"
    CORRUPT_CHECKPOINT = "corrupt_checkpoint"
    FAILED = "failed"


@dataclass(frozen=True)
class _PreparedResume:
    """Validated resume inputs after classification succeeds."""

    checkpoint: RunCheckpoint
    steps: list[StepDefinition]
    db: TasksDb | WorkflowsDb
