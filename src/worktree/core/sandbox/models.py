"""Pydantic and Enum models for Git worktree sandboxes."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class SandboxSession(BaseModel):
    """Metadata for one isolated background git worktree."""

    model_config = {"extra": "forbid", "strict": True}

    session_id: str
    target_branch: str
    sandbox_path: Path
    base_commit: str
    name: str | None = None
    created_at: str
    command_passed: bool | None = None
    wip_applied: bool = False
    wip_paths: list[str] = Field(default_factory=list)


class SandboxCreateStatus(StrEnum):
    """Classified outcomes for creating a sandbox worktree."""

    OK = "ok"
    CAPACITY_EXCEEDED = "capacity_exceeded"
    GIT_FAILED = "git_failed"
    GIT_TIMEOUT = "git_timeout"
    NOT_INITIALIZED = "not_initialized"
    UNREADABLE_CONFIG = "unreadable_config"
    WIP_FAILED = "wip_failed"


class SandboxCreateResult(BaseModel):
    """Non-raising result of sandbox creation."""

    model_config = {"extra": "forbid", "strict": True}

    status: SandboxCreateStatus
    session: SandboxSession | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when a sandbox session was created successfully."""
        return self.status == SandboxCreateStatus.OK and not self.errors


class SandboxApplyStrategy(StrEnum):
    """Supported strategies for applying sandbox changes to the main workspace."""

    PATCH = "patch"
    SQUASH = "squash"


class SandboxApplyStatus(StrEnum):
    """Classified outcomes for applying a sandbox."""

    OK = "ok"
    NOT_FOUND = "not_found"
    ALREADY_MERGED = "already_merged"
    MAIN_REPO_DIRTY = "main_repo_dirty"
    EMPTY_DIFF = "empty_diff"
    CONFLICT = "conflict"
    GIT_FAILED = "git_failed"


class SandboxApplyResult(BaseModel):
    """Structured result of applying sandbox changes."""

    model_config = {"extra": "forbid", "strict": True}

    status: SandboxApplyStatus
    sandbox_id: str
    strategy: SandboxApplyStrategy = SandboxApplyStrategy.PATCH
    touched_files: list[str] = Field(default_factory=list)
    conflicting_files: list[str] = Field(default_factory=list)
    cleaned_up: bool = False
    commit_sha: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when changes were applied successfully without errors."""
        return self.status == SandboxApplyStatus.OK and not self.errors


class SandboxDiffStatus(StrEnum):
    """Classified outcomes for inspecting sandbox diffs."""

    OK = "ok"
    NOT_FOUND = "not_found"
    EMPTY_DIFF = "empty_diff"
    GIT_FAILED = "git_failed"


class SandboxDiffResult(BaseModel):
    """Structured result of inspecting sandbox diffs."""

    model_config = {"extra": "forbid", "strict": True}

    status: SandboxDiffStatus
    sandbox_id: str
    diff_text: str = ""
    stat_text: str = ""
    files_changed: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when diff was generated successfully without errors."""
        return self.status == SandboxDiffStatus.OK and not self.errors
