"""
getworktree/commands/init.py

Handles local workspace initialization (`wt init`), setting up isolated
caching directories, default configuration files, and git safety rules.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import typer

from getworktree.common.utils import (
    print_dim,
    print_dim_bullet,
    print_error_panel,
    print_spacer,
    print_success,
)
from getworktree.core.bootstrap import bootstrap_worktree
from getworktree.core.db import init_database

# Baseline JSON configuration for new worktree projects
DEFAULT_CONFIG = {
    "version": "1.0.0",
    "created_at": None,  # Dynamically set on initialization
    "model_path": None,
    "sandbox": {"auto_clean": True, "max_background_runs": 3},
    "audit": {"db_path": ".worktree/token_audit.db"},
}

GITIGNORE_ENTRY = "\n# Worktree CLI cache and local databases\n/.worktree/\n"


def is_git_repository(path: Path) -> bool:
    """Check whether the given directory contains a .git directory or file."""
    git_path = path / ".git"
    return git_path.exists()


def ensure_config_file(config_path: Path, project_name: str) -> bool:
    """Generate default config.json if missing."""
    if not config_path.exists():
        config_data = DEFAULT_CONFIG.copy()
        config_data["project_name"] = project_name
        config_data["created_at"] = datetime.now(UTC).isoformat()

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        return True
    return False


def update_gitignore(gitignore_path: Path) -> bool:
    """Ensure /.worktree/ is excluded in .gitignore to prevent pushing cache profiles."""
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if "/.worktree/" in content or ".worktree" in content:
            return False  # Already present

        prefix = "" if content.endswith("\n") else "\n"
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write(f"{prefix}{GITIGNORE_ENTRY}")
        return True

    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write(GITIGNORE_ENTRY.lstrip())
    return True


def _display_path(cwd: Path, path: Path) -> str:
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        return path.as_posix()


def _render_bootstrap_failure(cwd: Path, errors: list[str]) -> None:
    lines = "\n".join(f"  {err}" for err in errors)
    remediation = (
        "\nFix:\n"
        "  resolve the path conflict above, then rerun [bold cyan]wt init[/bold cyan]."
    )
    print_error_panel("Failed to initialize Worktree:", f"{lines}{remediation}")


def _render_bootstrap_success(cwd: Path, result) -> None:
    worktree_label = _display_path(cwd, cwd / ".worktree")

    if result.repaired:
        print_success(f"Worktree structure repaired at {worktree_label}")
        print_dim("Created missing:")
        for path in result.dirs_created:
            print_dim_bullet(f"[cyan]{_display_path(cwd, path)}[/cyan]")
        return

    if result.root_created or result.dirs_created:
        print_success(f"Initialized Worktree at {worktree_label}")
        print_dim("Created:")
        for path in result.dirs_created:
            print_dim_bullet(f"[cyan]{_display_path(cwd, path)}[/cyan]")
        print_dim("\nNext: run [bold cyan]wt config show[/bold cyan] or [bold cyan]wt loop list[/bold cyan]")
        return

    print_success(f"Worktree already initialized at {worktree_label}")
    print_dim("No changes required.")


def init_command(*, tool_version: str | None = None):
    """
    Initialize a local project workspace for Worktree CLI and desktop sync.
    """
    cwd = Path.cwd().resolve()

    if not is_git_repository(cwd):
        print_error_panel(
            "Initialization Failed!",
            "The current directory is not a valid Git repository.\n"
            "Run [bold cyan]git init[/bold cyan] before running [bold cyan]wt init[/bold cyan].",
        )
        raise typer.Exit(code=1)

    worktree_dir = cwd / ".worktree"
    config_file = worktree_dir / "config.json"
    gitignore_file = cwd / ".gitignore"

    result = bootstrap_worktree(worktree_dir, tool_version=tool_version)
    if not result.ok:
        _render_bootstrap_failure(cwd, result.errors)
        raise typer.Exit(code=1)

    if result.root_created:
        update_gitignore(gitignore_file)

    ensure_config_file(config_file, project_name=cwd.name)
    init_database(cwd=cwd)

    print_spacer()
    _render_bootstrap_success(cwd, result)


app = typer.Typer()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        init_command()
