"""Handles local workspace initialization (`wt init`)."""

import json
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
from getworktree.core.config_generator import (
    CANONICAL_V1_DEFAULTS,
    generate_default_config,
)
from getworktree.core.db import init_database

GITIGNORE_ENTRY = "\n# Worktree CLI cache and local databases\n/.worktree/\n"


def is_git_repository(path: Path) -> bool:
    """Check whether the given directory contains a .git directory or file."""
    git_path = path / ".git"
    return git_path.exists()


def update_gitignore(gitignore_path: Path) -> bool:
    """Ensure /.worktree/ is excluded in .gitignore."""
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if "/.worktree/" in content or ".worktree" in content:
            return False

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


def _resolve_db_rel_path(config_file: Path) -> str:
    default = CANONICAL_V1_DEFAULTS["paths"]["db_path"]
    if not config_file.is_file():
        return default
    try:
        with open(config_file, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            paths = raw.get("paths")
            if isinstance(paths, dict) and paths.get("db_path"):
                return str(paths["db_path"])
    except (OSError, json.JSONDecodeError):
        pass
    return default


def _render_config_failure(errors: list[str]) -> None:
    lines = "\n".join(f"- {err}" for err in errors)
    print_error_panel("Failed to generate config:", lines)


def _render_config_result(cwd: Path, result) -> None:
    if not result.config_path:
        return
    label = f"./{_display_path(cwd, result.config_path)}"
    if result.created:
        print_dim_bullet(f"Generated config: [cyan]{label}[/cyan]")
    elif result.overwritten:
        print_dim_bullet(f"Regenerated config: [cyan]{label}[/cyan]")
    elif result.repaired:
        print_dim_bullet(f"Repaired config: [cyan]{label}[/cyan]")
        if result.inserted_keys:
            print_dim("  Added missing keys:")
            for key in result.inserted_keys:
                print_dim_bullet(f"[cyan]{key}[/cyan]")
    elif result.skipped_existing:
        print_dim_bullet(f"Config exists: [cyan]{label}[/cyan]")


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
        print_dim(
            "\nNext: run [bold cyan]wt config show[/bold cyan] or [bold cyan]wt loop list[/bold cyan]"
        )
        return

    print_success(f"Worktree already initialized at {worktree_label}")
    print_dim("No changes required.")


def init_command(
    *,
    tool_version: str | None = None,
    overwrite: bool = False,
    repair: bool = False,
):
    """Initialize a local project workspace for Worktree CLI and desktop sync."""
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

    config_result = generate_default_config(
        config_file,
        project_name=cwd.name,
        overwrite=overwrite,
        repair=repair,
    )
    if not config_result.ok:
        _render_config_failure(config_result.errors)
        raise typer.Exit(code=1)

    db_rel = _resolve_db_rel_path(config_file)
    init_database(cwd=cwd, db_rel_path=db_rel)

    print_spacer()
    _render_bootstrap_success(cwd, result)
    _render_config_result(cwd, config_result)
