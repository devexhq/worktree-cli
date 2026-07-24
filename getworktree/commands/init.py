"""
getworktree/commands/init.py

Handles local workspace initialization (`wt init`), setting up isolated
caching directories, default configuration files, and git safety rules.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()

# Baseline JSON configuration for new worktree projects
DEFAULT_CONFIG = {
    "version": "1.0.0",
    "created_at": None,  # Dynamically set on initialization
    "model_path": None,
    "sandbox": {
        "auto_clean": True,
        "max_background_runs": 3
    },
    "audit": {
        "db_path": ".worktree/token_audit.db"
    }
}

GITIGNORE_ENTRY = "\n# Worktree CLI cache and local databases\n/.worktree/\n"


def is_git_repository(path: Path) -> bool:
    """Check whether the given directory contains a .git directory or file."""
    git_path = path / ".git"
    return git_path.exists()


def ensure_worktree_dir(worktree_path: Path) -> bool:
    """Create .worktree directory if it doesn't already exist."""
    if not worktree_path.exists():
        worktree_path.mkdir(parents=True, exist_ok=True)
        return True
    return False


def ensure_config_file(config_path: Path, project_name: str) -> bool:
    """Generate default config.json if missing."""
    if not config_path.exists():
        config_data = DEFAULT_CONFIG.copy()
        config_data["project_name"] = project_name
        config_data["created_at"] = datetime.now(timezone.utc).isoformat()

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

        # Ensure proper trailing newline before appending
        prefix = "" if content.endswith("\n") else "\n"
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write(f"{prefix}{GITIGNORE_ENTRY}")
        return True
    else:
        # Create new .gitignore if it doesn't exist
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(GITIGNORE_ENTRY.lstrip())
        return True


def init_command():
    """
    Initialize a local project workspace for Worktree CLI and desktop sync.
    """
    cwd = Path.cwd().resolve()

    # 1. Verify valid Git repository
    if not is_git_repository(cwd):
        console.print(
            Panel.fit(
                "[bold red]Initialization Failed![/bold red]\n"
                "The current directory is not a valid Git repository.\n"
                "Run [bold cyan]git init[/bold cyan] before running [bold cyan]wt init[/bold cyan].",
                border_style="red"
            )
        )
        raise typer.Exit(code=1)

    worktree_dir = cwd / ".worktree"
    config_file = worktree_dir / "config.json"
    gitignore_file = cwd / ".gitignore"

    # 2. Provision directory & config
    dir_created = ensure_worktree_dir(worktree_dir)
    config_created = ensure_config_file(config_file, project_name=cwd.name)
    gitignore_updated = update_gitignore(gitignore_file)

    # 3. Output Status Report
    console.print("[bold green]✔ Worktree Workspace Initialized[/bold green]\n")

    if dir_created:
        console.print("  [dim]•[/dim] Created directory: [cyan]./.worktree/[/cyan]")
    else:
        console.print("  [dim]•[/dim] Directory exists:  [dim]./.worktree/[/dim]")

    if config_created:
        console.print("  [dim]•[/dim] Generated config:  [cyan]./.worktree/config.json[/cyan]")
    else:
        console.print("  [dim]•[/dim] Config exists:     [dim]./.worktree/config.json[/dim]")

    if gitignore_updated:
        console.print("  [dim]•[/dim] Updated exclusions: [cyan].gitignore[/cyan]")
    else:
        console.print("  [dim]•[/dim] Ignore state:     [dim].gitignore already configured[/dim]")

    console.print("\n[bold dim]Ready for local context extraction and agent runs.[/bold dim]")


# Typer command registration hook
app = typer.Typer()

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        init_command()
