"""Workspace initialization service."""

from __future__ import annotations

from pathlib import Path

from worktree.common.filesystem import Filesystem
from worktree.core.bootstrap.models import (
    InitFailureMode,
    WorkspaceInitResult,
)
from worktree.core.bootstrap.services.bootstrap import bootstrap_worktree
from worktree.core.catalog.services.seeder import seed_all_catalog_templates
from worktree.core.config import Config
from worktree.core.config.generator import generate_default_config
from worktree.core.db import init_database


def initialize_workspace(
    root: Path | None = None,
    *,
    tool_version: str | None = None,
    overwrite: bool = False,
    repair: bool = False,
) -> WorkspaceInitResult:
    """Initialize a local project workspace for Worktree CLI and desktop sync.

    Performs git preflight, bootstraps the .worktree/ directory tree, updates
    .gitignore, generates canonical default configuration, initializes the SQLite
    state database, and seeds starter catalog templates.
    """
    fs = Filesystem(root)
    resolved_root = fs.root_dir

    if not fs.is_git_repo():
        err = (
            "The current directory is not a valid Git repository.\n"
            "Run [bold cyan]git init[/bold cyan] before running [bold cyan]wt init[/bold cyan]."
        )
        return WorkspaceInitResult(errors=[err], failure_mode=InitFailureMode.PREFLIGHT)

    result = bootstrap_worktree(fs.worktree_dir, tool_version=tool_version)
    if not result.ok:
        return WorkspaceInitResult(
            bootstrap_result=result,
            errors=list(result.errors),
            failure_mode=InitFailureMode.BOOTSTRAP,
        )

    if result.root_created:
        fs.update_gitignore()

    config_result = generate_default_config(
        fs.config_file,
        project_name=resolved_root.name,
        overwrite=overwrite,
        repair=repair,
    )
    if not config_result.ok:
        return WorkspaceInitResult(
            bootstrap_result=result,
            config_result=config_result,
            errors=list(config_result.errors),
            failure_mode=InitFailureMode.CONFIG_GENERATION,
        )

    config = Config(resolved_root)
    init_database(path=resolved_root, db_rel_path=config.paths.db_path)

    seed_result = seed_all_catalog_templates(path=resolved_root)
    return WorkspaceInitResult(
        bootstrap_result=result,
        config_result=config_result,
        seed_result=seed_result,
        errors=list(seed_result.errors),
        failure_mode=None,
    )
