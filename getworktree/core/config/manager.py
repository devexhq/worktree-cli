"""Handles loading, validating, and extracting repository context from config."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

from getworktree.common.schema_validation import CONFIG_VALIDATOR

console = Console()


class ProjectConfig(BaseModel):
    """Project identity fields from config V1."""

    model_config = {"extra": "forbid", "strict": True}

    name: str
    initialized_at: str | None = None


class PathsConfig(BaseModel):
    """Filesystem layout paths from config V1."""

    model_config = {"extra": "forbid", "strict": True}

    root_dir: str = ".worktree"
    loops_dir: str = ".worktree/loops"
    sessions_dir: str = ".worktree/sessions"
    artifacts_dir: str = ".worktree/artifacts"
    db_path: str = ".worktree/token_audit.db"


class SandboxConfig(BaseModel):
    """Background sandbox lifecycle settings."""

    model_config = {"extra": "forbid", "strict": True}

    base_ref: str = "HEAD"
    auto_clean: bool = True
    keep_on_failure: bool = True
    max_active_sandboxes: int = 3
    default_timeout_seconds: int = 900


class LoopConfig(BaseModel):
    """Loop attempt and timeout defaults."""

    model_config = {"extra": "forbid", "strict": True}

    default_max_attempts: int = 5
    default_trigger_timeout_seconds: int = 600
    default_agent_timeout_seconds: int = 120
    max_attempts_hard_limit: int = 20
    detect_repeat_failures: bool = True


class AgentConfig(BaseModel):
    """Agent provider settings."""

    model_config = {"extra": "forbid", "strict": True}

    provider: str = "local"
    model: str | None = None
    endpoint: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096


class PatchConfig(BaseModel):
    """Patch application limits and strategy."""

    model_config = {"extra": "forbid", "strict": True}

    strategy: str = "unified_diff"
    max_files: int = 30
    max_patch_kb: int = 1024
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
    max_sessions: int = 1000


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
    artifact_ttl_days: int = 30


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


def get_current_git_branch(cwd: Path) -> str:
    """Extract current active Git branch using standard Git CLI."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        return branch if branch else "HEAD (detached)"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def load_raw_config(config_path: Path) -> dict[str, Any]:
    """Safely load JSON configuration file from disk."""
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found at '{config_path}'. Run 'wt init' first."
        )

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed config.json file at '{config_path}': {e}") from e
    if not isinstance(data, dict):
        raise ValueError(
            f"Malformed config.json file at '{config_path}': root must be an object"
        )
    return data


def parse_and_validate_config(raw: dict[str, Any]) -> WorktreeConfig:
    """Validate against V1 schema and map into typed structures."""
    validation = CONFIG_VALIDATOR.validate(raw)
    if not validation.ok:
        detail = "; ".join(validation.errors)
        raise ValueError(f"Config schema validation failed: {detail}")

    project_raw = raw.get("project") or {}
    project_name = project_raw.get("name") or "unnamed_project"
    normalized = {
        **raw,
        "project": {
            **project_raw,
            "name": str(project_name),
        },
    }
    return WorktreeConfig.model_validate(normalized)


def load_context(cwd: Path | None = None) -> WorktreeContext:
    """Load config and repo context with unified developer warnings."""
    root_dir = (cwd or Path.cwd()).resolve()
    config_path = root_dir / ".worktree" / "config.json"

    raw_json = load_raw_config(config_path)
    config = parse_and_validate_config(raw_json)
    current_branch = get_current_git_branch(root_dir)

    warnings: list[str] = []

    if not config.agent.model:
        warnings.append("Agent model is not configured (agent.model is null).")

    if current_branch in ("main", "master"):
        warnings.append(
            f"Active branch is '{current_branch}'. Automated loops on primary branches are discouraged."
        )

    if config.sandbox.max_active_sandboxes > 5:
        warnings.append(
            f"max_active_sandboxes ({config.sandbox.max_active_sandboxes}) is unusually high."
        )

    return WorktreeContext(
        config=config, current_branch=current_branch, warnings=warnings
    )


def display_context_warnings(context: WorktreeContext) -> None:
    """Print Rich-formatted warnings to stderr/stdout."""
    if context.warnings:
        console.print("[yellow]⚠️  Configuration & Context Warnings:[/yellow]")
        for w in context.warnings:
            console.print(f"  [dim]•[/dim] [yellow]{w}[/yellow]")
