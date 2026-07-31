"""Handles local workspace initialization (`wt init`)."""

from pathlib import Path

import typer

from getworktree.common.fs import (
    get_gitignore_file,
    get_worktree_config_file,
    get_worktree_dir,
    is_git_repository,
    update_gitignore,
)
from getworktree.common.utils import (
    RichOutput,
    display_path,
    resolve_path_from_config,
)
from getworktree.core.bootstrap import bootstrap_worktree
from getworktree.core.config.generator import generate_default_config
from getworktree.core.db import init_database
from getworktree.core.loops.seeder import seed_starter_loops

rich_output = RichOutput()


def _render_config_result(cwd: Path, result) -> None:
    if not result.config_path:
        return
    
    rich_output.spacer()

    label = f"./{display_path(result.config_path, cwd)}"
    if result.created:
        rich_output.dim_bullet(f"Generated config: [cyan]{label}[/cyan]")
    elif result.overwritten:
        rich_output.dim_bullet(f"Regenerated config: [cyan]{label}[/cyan]")
    elif result.repaired:
        rich_output.dim_bullet(f"Repaired config: [cyan]{label}[/cyan]")
        if result.inserted_keys:
            rich_output.dim_text("  Added missing keys:")
            for key in result.inserted_keys:
                rich_output.dim_bullet(f"[cyan]{key}[/cyan]")
    elif result.skipped_existing:
        rich_output.dim_bullet(f"Config exists: [cyan]{label}[/cyan]")


def _render_bootstrap_failure(cwd: Path, errors: list[str]) -> None:
    lines = "\n".join(f"  {err}" for err in errors)
    remediation = (
        "\nFix:\n"
        "  resolve the path conflict above, then rerun [bold cyan]wt init[/bold cyan]."
    )
    rich_output.error_panel("Failed to initialize Worktree:", f"{lines}{remediation}")


def _render_bootstrap_success(cwd: Path, result) -> None:
    worktree_label = display_path(cwd / ".worktree", cwd)

    if result.repaired:
        rich_output.success(f"Worktree structure repaired at {worktree_label}")
        rich_output.dim_text("Created missing:")
        for path in result.dirs_created:
            rich_output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")
        return

    if result.root_created or result.dirs_created:
        rich_output.success(f"Initialized Worktree at {worktree_label}")
        rich_output.dim_text("Created:")
        for path in result.dirs_created:
            rich_output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")
        return

    rich_output.success(f"Worktree already initialized at {worktree_label}")
    rich_output.dim_text("No changes required.")


def _render_config_failure(errors: list[str]) -> None:
    lines = "\n".join(f"- {err}" for err in errors)
    rich_output.error_panel("Failed to generate config:", lines)


def _render_loop_seed_result(cwd: Path, result) -> None:
    rich_output.spacer()
    if result.created_files:
        rich_output.success("Seeded starter loops")
        rich_output.dim_text("Created:")
        for path in result.created_files:
            rich_output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")
    elif result.overwritten_files:
        rich_output.success("Refreshed starter loops")
    else:
        rich_output.success("Starter loops already present")

    if result.skipped_existing_files:
        rich_output.dim_text("Skipped existing:")
        for path in result.skipped_existing_files:
            rich_output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")

    if result.errors:
        lines = "\n".join(f"- {err}" for err in result.errors)
        rich_output.error_panel("Starter loop seeding failed:", lines)


def init_command(
    *,
    tool_version: str | None = None,
    overwrite: bool = False,
    repair: bool = False,
):
    """Initialize a local project workspace for Worktree CLI and desktop sync."""
    cwd = Path.cwd().resolve()

    if not is_git_repository(cwd):
        rich_output.error_panel(
            "Initialization Failed!",
            "The current directory is not a valid Git repository.\n"
            "Run [bold cyan]git init[/bold cyan] before running [bold cyan]wt init[/bold cyan].",
        )
        raise typer.Exit(code=1)

    result = bootstrap_worktree(get_worktree_dir(cwd), tool_version=tool_version)
    if not result.ok:
        _render_bootstrap_failure(cwd, result.errors)
        raise typer.Exit(code=1)

    if result.root_created:
        update_gitignore(get_gitignore_file(cwd))

    config_result = generate_default_config(
        get_worktree_config_file(cwd),
        project_name=cwd.name,
        overwrite=overwrite,
        repair=repair,
    )
    if not config_result.ok:
        _render_config_failure(config_result.errors)
        raise typer.Exit(code=1)

    db_rel = resolve_path_from_config(
        get_worktree_config_file(cwd), "db_path", get_worktree_dir(cwd) / "db.sqlite"
    )
    init_database(cwd=cwd, db_rel_path=str(db_rel))

    loop_seed_result = seed_starter_loops(get_worktree_dir(cwd) / "loops")
    if loop_seed_result.errors:
        _render_loop_seed_result(cwd, loop_seed_result)
        raise typer.Exit(code=1)

    rich_output.spacer()
    _render_bootstrap_success(cwd, result)
    _render_config_result(cwd, config_result)
    _render_loop_seed_result(cwd, loop_seed_result)
    rich_output.spacer()
    rich_output.dim_text(
        "Next: run [bold cyan]wt config show[/bold cyan] or [bold cyan]wt loop list[/bold cyan]"
    )
