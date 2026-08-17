"""Handles local workspace initialization (`wt init`)."""

from pathlib import Path

import typer

from worktree.common.fs import (
    get_gitignore_file,
    get_worktree_config_file,
    get_worktree_dir,
    is_git_repository,
    update_gitignore,
)
from worktree.common.utils import RichOutput
from worktree.core.bootstrap import bootstrap_worktree
from worktree.core.catalog.services.seeder import seed_all_catalog_templates
from worktree.core.config.generator import generate_default_config
from worktree.core.config.loader import load_config_result
from worktree.core.config.models import PathsConfig
from worktree.core.db import init_database

from .models import InitCommandOutcome
from .renderers import (
    render_init_bootstrap_failure,
    render_init_config_failure,
    render_init_outcome,
)

rich_output = RichOutput()


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
        render_init_bootstrap_failure(cwd, result.errors, rich_output=rich_output)
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
        render_init_config_failure(config_result.errors, rich_output=rich_output)
        raise typer.Exit(code=1)

    db_rel = PathsConfig().db_path
    loaded = load_config_result(cwd=cwd)
    if loaded.ok and loaded.config is not None:
        db_rel = loaded.config.paths.db_path
    init_database(cwd=cwd, db_rel_path=db_rel)

    seed_result = seed_all_catalog_templates(cwd=cwd)
    if seed_result.errors:
        outcome = InitCommandOutcome(
            bootstrap_result=result,
            config_result=config_result,
            seed_result=seed_result,
        )
        render_init_outcome(cwd, outcome, rich_output=rich_output)
        raise typer.Exit(code=1)

    outcome = InitCommandOutcome(
        bootstrap_result=result,
        config_result=config_result,
        seed_result=seed_result,
    )
    render_init_outcome(cwd, outcome, rich_output=rich_output)
