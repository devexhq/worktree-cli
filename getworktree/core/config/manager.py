"""Handles loading, validating, and extracting repository context from config."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from rich.console import Console

from getworktree.common.schema_validation import SchemaValidator

console = Console()
CONFIG_VALIDATOR = SchemaValidator(
    resources.files("getworktree.schemas") / "config_v1.json"
)


@dataclass
class ProjectConfig:
    """Project identity fields from config V1."""

    name: str
    initialized_at: str | None = None


@dataclass
class PathsConfig:
    """Filesystem layout paths from config V1."""

    root_dir: str = ".worktree"
    loops_dir: str = ".worktree/loops"
    sessions_dir: str = ".worktree/sessions"
    artifacts_dir: str = ".worktree/artifacts"
    db_path: str = ".worktree/token_audit.db"


@dataclass
class SandboxConfig:
    """Background sandbox lifecycle settings."""

    base_ref: str = "HEAD"
    auto_clean: bool = True
    keep_on_failure: bool = True
    max_active_sandboxes: int = 3
    default_timeout_seconds: int = 900


@dataclass
class AgentConfig:
    """Agent provider settings."""

    provider: str = "local"
    model: str | None = None
    endpoint: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096


@dataclass
class WorktreeConfig:
    """Parsed `.worktree/config.json` V1 payload."""

    version: int
    project: ProjectConfig
    paths: PathsConfig = field(default_factory=PathsConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)

    @property
    def project_name(self) -> str:
        """Compatibility alias for project display name."""
        return self.project.name


@dataclass
class WorktreeContext:
    """Config plus live Git branch and aggregated warnings."""

    config: WorktreeConfig
    current_branch: str
    warnings: list[str] = field(default_factory=list)


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

    project_raw = raw.get("project", {})
    paths_raw = raw.get("paths", {})
    sandbox_raw = raw.get("sandbox", {})
    agent_raw = raw.get("agent", {})

    project = ProjectConfig(
        name=str(project_raw.get("name") or "unnamed_project"),
        initialized_at=project_raw.get("initialized_at"),
    )
    paths = PathsConfig(
        root_dir=str(paths_raw.get("root_dir", ".worktree")),
        loops_dir=str(paths_raw.get("loops_dir", ".worktree/loops")),
        sessions_dir=str(paths_raw.get("sessions_dir", ".worktree/sessions")),
        artifacts_dir=str(paths_raw.get("artifacts_dir", ".worktree/artifacts")),
        db_path=str(paths_raw.get("db_path", ".worktree/token_audit.db")),
    )
    sandbox = SandboxConfig(
        base_ref=str(sandbox_raw.get("base_ref", "HEAD")),
        auto_clean=bool(sandbox_raw.get("auto_clean", True)),
        keep_on_failure=bool(sandbox_raw.get("keep_on_failure", True)),
        max_active_sandboxes=int(sandbox_raw.get("max_active_sandboxes", 3)),
        default_timeout_seconds=int(sandbox_raw.get("default_timeout_seconds", 900)),
    )
    agent = AgentConfig(
        provider=str(agent_raw.get("provider", "local")),
        model=agent_raw.get("model"),
        endpoint=agent_raw.get("endpoint"),
        temperature=float(agent_raw.get("temperature", 0.2)),
        max_tokens=int(agent_raw.get("max_tokens", 4096)),
    )

    return WorktreeConfig(
        version=int(raw["version"]),
        project=project,
        paths=paths,
        sandbox=sandbox,
        agent=agent,
    )


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
