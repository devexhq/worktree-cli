"""Handles local workspace initialization (`wt init`)."""

from __future__ import annotations

from worktree.cli.context import CliContext
from worktree.cli.ui.dispatcher import ui_dispatcher
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


def init_command(
    context: CliContext,
    tool_version: str | None = None,
    overwrite: bool = False,
    repair: bool = False,
    output_format: str = "terminal",
) -> InitCommandOutcome:
    """Initialize a local project workspace for Worktree CLI and desktop sync."""
    root = context.cwd

    if not is_git_repository(root):
        err = (
            "The current directory is not a valid Git repository.\n"
            "Run [bold cyan]git init[/bold cyan] before running [bold cyan]wt init[/bold cyan]."
        )
        outcome = InitCommandOutcome(errors=[err])
        ui_dispatcher.dispatch(outcome, output_format=output_format)
        return outcome

    result = bootstrap_worktree(get_worktree_dir(root), tool_version=tool_version)
    if not result.ok:
        outcome = InitCommandOutcome(bootstrap_result=result, errors=list(result.errors))
        ui_dispatcher.dispatch(outcome, output_format=output_format)
        return outcome

    if result.root_created:
        update_gitignore(get_gitignore_file(root))

    config_result = generate_default_config(
        get_worktree_config_file(root),
        project_name=root.name,
        overwrite=overwrite,
        repair=repair,
    )
    if not config_result.ok:
        outcome = InitCommandOutcome(
            bootstrap_result=result,
            config_result=config_result,
            errors=list(config_result.errors),
        )
        ui_dispatcher.dispatch(outcome, output_format=output_format)
        return outcome

    db_rel = PathsConfig().db_path
    loaded = load_config_result(path=root)
    if loaded.ok and loaded.config is not None:
        db_rel = loaded.config.paths.db_path
    init_database(path=root, db_rel_path=db_rel)

    seed_result = seed_all_catalog_templates(path=root)
    outcome = InitCommandOutcome(
        bootstrap_result=result,
        config_result=config_result,
        seed_result=seed_result,
        errors=list(seed_result.errors),
    )
    ui_dispatcher.dispatch(outcome, output_format=output_format)
    return outcome
