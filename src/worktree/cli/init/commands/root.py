"""Handles local workspace initialization (`wt init`)."""

from __future__ import annotations

import typer

from worktree.cli.context import Context
from worktree.common.fs import (
    get_gitignore_file,
    get_worktree_config_file,
    get_worktree_dir,
    is_git_repository,
    update_gitignore,
)
from worktree.core.bootstrap import bootstrap_worktree
from worktree.core.catalog.services.seeder import seed_all_catalog_templates
from worktree.core.config.generator import generate_default_config
from worktree.core.config.loader import load_config_result
from worktree.core.config.models import PathsConfig
from worktree.core.db import init_database

from ..models import InitCommandOutcome
from ..renderers import (
    render_init_bootstrap_failure,
    render_init_config_failure,
    render_init_outcome,
)


def init_command(
    *,
    context: Context,
    tool_version: str | None = None,
    overwrite: bool = False,
    repair: bool = False,
) -> None:
    """Initialize a local project workspace for Worktree CLI and desktop sync."""
    output = context.output
    root = context.cwd

    if not is_git_repository(root):
        output.error_panel(
            "Initialization Failed!",
            "The current directory is not a valid Git repository.\n"
            "Run [bold cyan]git init[/bold cyan] before running [bold cyan]wt init[/bold cyan].",
        )
        output.print()
        raise typer.Exit(code=1)

    result = bootstrap_worktree(get_worktree_dir(root), tool_version=tool_version)
    if not result.ok:
        render_init_bootstrap_failure(root, result.errors, output=output)
        output.print()
        raise typer.Exit(code=1)

    if result.root_created:
        update_gitignore(get_gitignore_file(root))

    config_result = generate_default_config(
        get_worktree_config_file(root),
        project_name=root.name,
        overwrite=overwrite,
        repair=repair,
    )
    if not config_result.ok:
        render_init_config_failure(config_result.errors, output=output)
        output.print()
        raise typer.Exit(code=1)

    db_rel = PathsConfig().db_path
    loaded = load_config_result(path=root)
    if loaded.ok and loaded.config is not None:
        db_rel = loaded.config.paths.db_path
    init_database(path=root, db_rel_path=db_rel)

    seed_result = seed_all_catalog_templates(path=root)
    if seed_result.errors:
        outcome = InitCommandOutcome(
            bootstrap_result=result,
            config_result=config_result,
            seed_result=seed_result,
        )
        render_init_outcome(root, outcome, output=output)
        output.print()
        raise typer.Exit(code=1)

    outcome = InitCommandOutcome(
        bootstrap_result=result,
        config_result=config_result,
        seed_result=seed_result,
    )
    render_init_outcome(root, outcome, output=output)
    output.print()
