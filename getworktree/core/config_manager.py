"""
getworktree/core/config_manager.py

Handles loading, validating, and extracting repository context from ./.worktree/config.json
and active Git branch states.
"""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


@dataclass
class SandboxConfig:
    auto_clean: bool = True
    max_background_runs: int = 3


@dataclass
class AuditConfig:
    db_path: str = ".worktree/token_audit.db"


@dataclass
class WorktreeConfig:
    version: str
    project_name: str
    created_at: str | None = None
    model_path: str | None = None
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)


@dataclass
class WorktreeContext:
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
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed config.json file at '{config_path}': {e}") from e


def parse_and_validate_config(raw: dict[str, Any]) -> WorktreeConfig:
    """Validate JSON payload layout and map into strongly-typed data structures."""
    version = raw.get("version", "1.0.0")
    project_name = raw.get("project_name", "unnamed_project")
    created_at = raw.get("created_at")
    model_path = raw.get("model_path")

    # Sandbox config parsing
    sandbox_raw = raw.get("sandbox", {})
    sandbox_cfg = SandboxConfig(
        auto_clean=bool(sandbox_raw.get("auto_clean", True)),
        max_background_runs=int(sandbox_raw.get("max_background_runs", 3)),
    )

    # Audit config parsing
    audit_raw = raw.get("audit", {})
    audit_cfg = AuditConfig(
        db_path=str(audit_raw.get("db_path", ".worktree/token_audit.db"))
    )

    return WorktreeConfig(
        version=version,
        project_name=project_name,
        created_at=created_at,
        model_path=model_path,
        sandbox=sandbox_cfg,
        audit=audit_cfg,
    )


def load_context(cwd: Path | None = None) -> WorktreeContext:
    """
    Primary API entry point to extract local repo state, load config,
    and aggregate unified developer warnings.
    """
    root_dir = (cwd or Path.cwd()).resolve()
    config_path = root_dir / ".worktree" / "config.json"

    raw_json = load_raw_config(config_path)
    config = parse_and_validate_config(raw_json)
    current_branch = get_current_git_branch(root_dir)

    warnings: list[str] = []

    # Check warning bounds
    if not config.model_path:
        warnings.append("Model path is not configured (model_path is null).")

    if current_branch in ("main", "master"):
        warnings.append(
            f"Active branch is '{current_branch}'. Automated loops on primary branches are discouraged."
        )

    if config.sandbox.max_background_runs > 5:
        warnings.append(
            f"max_background_runs ({config.sandbox.max_background_runs}) is unusually high."
        )

    return WorktreeContext(
        config=config, current_branch=current_branch, warnings=warnings
    )


def display_context_warnings(context: WorktreeContext) -> None:
    """Utility helper to print Rich-formatted warnings to stderr/stdout."""
    if context.warnings:
        console.print("[yellow]⚠️  Configuration & Context Warnings:[/yellow]")
        for w in context.warnings:
            console.print(f"  [dim]•[/dim] [yellow]{w}[/yellow]")
