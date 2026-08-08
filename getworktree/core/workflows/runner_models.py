"""Run-result models and callback type aliases for the workflow iteration runner.

Scoped to the *runtime* shapes produced/consumed by ``run_workflow_iteration``
(status enums, attempt/outcome records, and the injectable callback
signatures). Workflow *definition* schema (parsed from YAML) lives in
``core/workflows/models.py`` instead.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from getworktree.core.git_sandbox import SandboxCreateResult, SandboxSession
from getworktree.core.workflows.patch import PatchApplyResult
from getworktree.core.workflows.payload import AgentFailurePayload
from getworktree.core.workflows.trigger import TriggerRunResult

if TYPE_CHECKING:
    from getworktree.core.config.models import WorktreeConfig
    from getworktree.core.workflows.agents.base import AgentAdapter


class WorkflowFinalStatus(StrEnum):
    """Terminal status for one workflow run session."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    UNFIXABLE = "UNFIXABLE"
    ABORTED = "ABORTED"


class StopReason(StrEnum):
    """Terminal ``stop_reason`` values recorded on a workflow run.

    These strings are part of the documented contract in
    ``docs/agents/architecture.md``; the enum only names the existing
    literals, it does not change any wire value.
    """

    MAX_ATTEMPTS_EXHAUSTED = "max_attempts_exhausted"
    TRIGGER_PASSED = "trigger_passed"
    USER_ABORT = "user_abort"
    SESSION_TIMEOUT = "session_timeout"
    AGENT_UNFIXABLE = "agent_unfixable"
    CONFIGURATION_ERROR = "configuration_error"
    SANDBOX_CREATE_FAILED = "sandbox_create_failed"
    REPEAT_FAILURE_SIGNATURE = "repeat_failure_signature"
    AGENT_NO_OP_STREAK = "agent_no_op_streak"


class AttemptRecord(BaseModel):
    """One attempt within a workflow run."""

    model_config = {"extra": "forbid", "strict": True}

    attempt: int
    trigger_status: str | None = None
    agent_status: str | None = None
    patch_status: str | None = None
    errors: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    trigger_exit_code: int | None = None
    trigger_duration_ms: int | None = None
    agent_duration_ms: int | None = None
    patch_touched_files: list[str] = Field(default_factory=list)
    trigger_stdout: str = ""
    trigger_stderr: str = ""


class StepOutcome(BaseModel):
    """Result of a single workflow step, dispatched on by the attempt workflow.

    ``continue_workflow`` distinguishes "keep iterating" from "stop now". When
    stopping, ``final_status``/``stop_reason``/``command_passed`` carry the
    terminal values the caller should assign before breaking.
    """

    model_config = {"extra": "forbid", "strict": True}

    continue_workflow: bool
    final_status: WorkflowFinalStatus | None = None
    stop_reason: str | None = None
    command_passed: bool | None = None


class WorkflowRunResult(BaseModel):
    """Structured outcome of ``run_workflow_iteration``."""

    model_config = {"extra": "forbid", "strict": True}

    status: WorkflowFinalStatus
    session_id: str
    workflow_name: str
    sandbox_path: Path | None = None
    attempts: list[AttemptRecord] = Field(default_factory=list)
    stop_reason: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    max_attempts: int = 0
    sandbox_retained: bool = False

    @property
    def ok(self) -> bool:
        """Return True only when the workflow finished with PASSED."""
        return self.status == WorkflowFinalStatus.PASSED


ApprovePatchFn = Callable[[str], bool]
ListChangedFilesFn = Callable[[Path], list[str]]
RunTriggerFn = Callable[..., TriggerRunResult]
ApplyPatchFn = Callable[..., PatchApplyResult]
DiscardMutationFn = Callable[[Path, str], None]
BuildPayloadFn = Callable[..., AgentFailurePayload]
OnAttemptEndFn = Callable[[AttemptRecord], None]
OnEventFn = Callable[[str, dict[str, Any]], None]
IsAbortedFn = Callable[[], bool]
CreateSandboxFn = Callable[[], SandboxCreateResult]
CleanupSandboxFn = Callable[[SandboxSession], None]


@dataclass(kw_only=True)
class WorkflowRunOptions:
    """Runtime invocation overrides and event callbacks for a workflow execution session."""

    max_attempts: int | None = None
    require_before_apply: bool | None = None
    auto_clean: bool | None = None
    keep_on_failure: bool | None = None
    stop_when: set[str] | None = None
    include_wip: bool = False
    prompt_dump_dir: Path | None = None
    session_timeout_seconds: float | int | None = None
    session_id: str | None = None
    config: WorktreeConfig | None = None
    no_sandbox: bool = False

    agent: AgentAdapter | None = None
    on_event: OnEventFn | None = None
    on_attempt_end: OnAttemptEndFn | None = None
    approve_patch: ApprovePatchFn | None = None
    abort_event: threading.Event | None = None
