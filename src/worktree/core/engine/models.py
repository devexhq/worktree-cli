"""Result types for the blueprint execution engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from worktree.core.runtime.models import FailurePrompter, RunObserver


class EngineResumeStatus(StrEnum):
    """Classified outcomes for ``ResumableRun.load`` / ``Engine.resume``."""

    OK = "ok"
    NOT_FOUND = "not_found"
    WRONG_STATUS = "wrong_status"
    MISSING_SANDBOX = "missing_sandbox"
    CORRUPT_CHECKPOINT = "corrupt_checkpoint"
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
    non_interactive: bool = False
