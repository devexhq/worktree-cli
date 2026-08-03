"""Pydantic models for `.worktree/config.json` V1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AgentProvider = Literal["local", "openai", "anthropic", "azure_openai", "custom"]
PatchStrategy = Literal["unified_diff"]


class ProjectConfig(BaseModel):
    """Project identity fields from config V1."""

    model_config = {"extra": "forbid", "strict": True}

    name: str
    initialized_at: str | None = None


class PathsConfig(BaseModel):
    """Filesystem layout paths from config V1."""

    model_config = {"extra": "forbid", "strict": True}

    root_dir: str = Field(default=".worktree", min_length=1)
    loops_dir: str = Field(default=".worktree/loops", min_length=1)
    sessions_dir: str = Field(default=".worktree/sessions", min_length=1)
    artifacts_dir: str = Field(default=".worktree/artifacts", min_length=1)
    db_path: str = Field(default=".worktree/token_audit.db", min_length=1)


class SandboxConfig(BaseModel):
    """Background sandbox lifecycle settings."""

    model_config = {"extra": "forbid", "strict": True}

    base_ref: str = Field(default="HEAD", min_length=1)
    auto_clean: bool = True
    keep_on_failure: bool = True
    max_active_sandboxes: int = Field(default=3, ge=1)
    default_timeout_seconds: int = Field(default=900, ge=1)


class LoopConfig(BaseModel):
    """Loop attempt and timeout defaults."""

    model_config = {"extra": "forbid", "strict": True}

    default_max_attempts: int = Field(default=5, ge=1)
    default_trigger_timeout_seconds: int = Field(default=600, ge=1)
    default_agent_timeout_seconds: int = Field(default=120, ge=1)
    max_attempts_hard_limit: int = Field(default=20, ge=1)
    detect_repeat_failures: bool = True


class AgentConfig(BaseModel):
    """Agent provider settings."""

    model_config = {"extra": "forbid", "strict": True}

    provider: AgentProvider = "local"
    model: str | None = Field(default=None, min_length=1)
    endpoint: str | None = Field(default=None, min_length=1)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)


class PatchConfig(BaseModel):
    """Patch application limits and strategy."""

    model_config = {"extra": "forbid", "strict": True}

    strategy: PatchStrategy = "unified_diff"
    max_files: int = Field(default=30, ge=1)
    max_patch_kb: int = Field(default=1024, ge=1)
    reject_binary_changes: bool = True


class ApprovalConfig(BaseModel):
    """Human-approval gates before applying changes."""

    model_config = {"extra": "forbid", "strict": True}

    require_before_apply: bool = True
    require_before_final_apply: bool = True


class HistoryConfig(BaseModel):
    """Session history retention settings."""

    model_config = {"extra": "forbid", "strict": True}

    save_attempt_logs: bool = True
    save_agent_payloads: bool = True
    save_final_diff: bool = True
    max_sessions: int = Field(default=1000, ge=1)


class DoctorConfig(BaseModel):
    """Doctor command check toggles."""

    model_config = {"extra": "forbid", "strict": True}

    check_git: bool = True
    check_paths_writable: bool = True
    check_config_schema: bool = True
    check_stale_worktrees: bool = True
    check_required_binaries: bool = True


class PruneConfig(BaseModel):
    """Prune command cleanup toggles."""

    model_config = {"extra": "forbid", "strict": True}

    remove_stale_worktrees: bool = True
    remove_orphaned_sandboxes: bool = True
    remove_expired_artifacts: bool = False
    artifact_ttl_days: int = Field(default=30, ge=0)


class TelemetryConfig(BaseModel):
    """Optional telemetry settings."""

    model_config = {"extra": "forbid", "strict": True}

    enabled: bool = False


class WorktreeConfig(BaseModel):
    """Parsed `.worktree/config.json` V1 payload."""

    model_config = {"extra": "forbid", "strict": True}

    version: int
    project: ProjectConfig
    paths: PathsConfig = Field(default_factory=PathsConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    patch: PatchConfig = Field(default_factory=PatchConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    doctor: DoctorConfig = Field(default_factory=DoctorConfig)
    prune: PruneConfig = Field(default_factory=PruneConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

    @property
    def project_name(self) -> str:
        """Compatibility alias for project display name."""
        return self.project.name


class WorktreeContext(BaseModel):
    """Config plus live Git branch and aggregated warnings."""

    model_config = {"extra": "forbid", "strict": True}

    config: WorktreeConfig
    current_branch: str
    warnings: list[str] = Field(default_factory=list)
