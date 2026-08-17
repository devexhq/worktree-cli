"""Repository context and developer warnings derived from loaded config."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from worktree.common.constants import GIT_SUBPROCESS_TIMEOUT_SECONDS
from worktree.core.config.loader import load_config
from worktree.core.config.models import WorktreeContext

console = Console()


def get_current_git_branch(cwd: Path) -> str:
    """Extract current active Git branch using standard Git CLI."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
        branch = result.stdout.strip()
        return branch if branch else "HEAD (detached)"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def load_context(cwd: Path | None = None) -> WorktreeContext:
    """Load config and repo context with unified developer warnings."""
    root_dir = (cwd or Path.cwd()).resolve()
    config = load_config(cwd=root_dir)
    current_branch = get_current_git_branch(root_dir)

    warnings: list[str] = []

    if not config.agent.model:
        warnings.append("Agent model is not configured (agent.model is null).")

    if current_branch in ("main", "master"):
        warnings.append(
            f"Active branch is '{current_branch}'. Automated workflows on primary branches are discouraged."
        )

    if config.sandbox.max_active_sandboxes > 5:
        warnings.append(f"max_active_sandboxes ({config.sandbox.max_active_sandboxes}) is unusually high.")

    return WorktreeContext(config=config, current_branch=current_branch, warnings=warnings)


def display_context_warnings(context: WorktreeContext) -> None:
    """Print Rich-formatted warnings to stderr/stdout."""
    if context.warnings:
        console.print("[yellow]⚠️  Configuration & Context Warnings:[/yellow]")
        for w in context.warnings:
            console.print(f"  [dim]•[/dim] [yellow]{w}[/yellow]")
