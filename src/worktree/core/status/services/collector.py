"""Unified workspace health and runtime status collector."""

from __future__ import annotations

from pathlib import Path

from worktree.common.fs import find_worktree_root, scan_yaml_directory
from worktree.core.config.loader import ConfigLoadStatus, load_config_result
from worktree.core.db import (
    RunsRepository,
    SandboxesRepository,
    SandboxStatus,
)
from worktree.core.git import (
    GitCommandError,
    GitNotFoundError,
    GitPlumbingTimeoutError,
    GitRunner,
)
from worktree.core.status.models import (
    CatalogStatusInfo,
    ConfigStatusInfo,
    DatabaseStatusInfo,
    GitStatusInfo,
    SandboxStatusInfo,
    WorktreeStatusResult,
)


def _collect_git_status(root_dir: Path) -> GitStatusInfo:
    """Collect git repository branch, dirty status, and uncommitted file count."""
    try:
        is_inside = GitRunner.run(["rev-parse", "--is-inside-work-tree"], path=root_dir).strip()
        if is_inside != "true":
            return GitStatusInfo(
                is_git_repo=False,
                branch="none",
                is_dirty=False,
                uncommitted_files=0,
            )
        branch = GitRunner.get_current_branch(root_dir)
        status_lines = GitRunner.status_porcelain(root_dir)
        return GitStatusInfo(
            is_git_repo=True,
            branch=branch,
            is_dirty=bool(status_lines),
            uncommitted_files=len(status_lines),
        )
    except (GitNotFoundError, GitPlumbingTimeoutError):
        return GitStatusInfo(
            is_git_repo=False,
            branch="unknown",
            is_dirty=False,
            uncommitted_files=0,
        )
    except GitCommandError:
        return GitStatusInfo(
            is_git_repo=False,
            branch="none",
            is_dirty=False,
            uncommitted_files=0,
        )


def _collect_config_status(root_dir: Path) -> ConfigStatusInfo:
    """Collect configuration file status without mutations."""
    result = load_config_result(path=root_dir)
    return ConfigStatusInfo(
        status=result.status,
        config_path=result.config_path,
        is_valid=result.ok,
        config=result.config,
        errors=result.errors,
    )


def _scan_catalog_category(category_dir: Path) -> tuple[int, int, list[str]]:
    """Scan a catalog category directory, returning (total_count, invalid_count, item_names)."""
    if not category_dir.is_dir():
        return 0, 0, []

    entries = scan_yaml_directory(category_dir)
    invalid_count = 0
    names: list[str] = []

    for entry in entries:
        names.append(entry.name)
        if entry.error is not None or entry.parsed is None or not isinstance(entry.parsed, dict):
            invalid_count += 1

    return len(entries), invalid_count, names


def _collect_catalog_status(root_dir: Path) -> CatalogStatusInfo:
    """Collect blueprint catalog directory health and item counts."""
    catalog_dir = root_dir / ".worktree" / "catalog"
    if not catalog_dir.is_dir():
        return CatalogStatusInfo(
            exists=False,
            catalog_dir=catalog_dir,
            total_items=0,
            workflows_count=0,
            tasks_count=0,
            steps_count=0,
            invalid_items=0,
            item_names=[],
        )

    workflows_count, invalid_workflows, workflow_names = _scan_catalog_category(catalog_dir / "workflows")
    tasks_count, invalid_tasks, task_names = _scan_catalog_category(catalog_dir / "tasks")
    steps_count, invalid_steps, step_names = _scan_catalog_category(catalog_dir / "steps")

    total_items = workflows_count + tasks_count + steps_count
    invalid_items = invalid_workflows + invalid_tasks + invalid_steps
    item_names = [*workflow_names, *task_names, *step_names]

    return CatalogStatusInfo(
        exists=True,
        catalog_dir=catalog_dir,
        total_items=total_items,
        workflows_count=workflows_count,
        tasks_count=tasks_count,
        steps_count=steps_count,
        invalid_items=invalid_items,
        item_names=item_names,
    )


def _collect_database_status(root_dir: Path) -> DatabaseStatusInfo:
    """Collect SQLite database accessibility and total recorded runs."""
    db_path = root_dir / ".worktree" / "data.db"
    if not db_path.is_file():
        return DatabaseStatusInfo(
            exists=False,
            db_path=db_path,
            is_accessible=False,
            total_runs=0,
        )

    try:
        runs_repo = RunsRepository(root_dir, auto_init=False)
        total_runs = len(runs_repo.list())
        return DatabaseStatusInfo(
            exists=True,
            db_path=db_path,
            is_accessible=True,
            total_runs=total_runs,
        )
    except Exception:
        return DatabaseStatusInfo(
            exists=True,
            db_path=db_path,
            is_accessible=False,
            total_runs=0,
        )


def _collect_sandbox_status(
    root_dir: Path,
    config_status: ConfigStatusInfo,
    database_status: DatabaseStatusInfo,
) -> SandboxStatusInfo:
    """Collect active and total sandboxes with configured concurrency limits."""
    max_active_sandboxes = (
        config_status.config.sandbox.max_active_sandboxes
        if (config_status.is_valid and config_status.config is not None)
        else 5
    )

    sandboxes_dir = root_dir / ".worktree" / "sandboxes"

    if database_status.is_accessible:
        try:
            sandboxes_repo = SandboxesRepository(root_dir, auto_init=False)
            active_sandboxes = len(sandboxes_repo.list(status=SandboxStatus.ACTIVE))
            total_sandboxes = len(sandboxes_repo.list())
            return SandboxStatusInfo(
                active_sandboxes=active_sandboxes,
                total_sandboxes=total_sandboxes,
                max_active_sandboxes=max_active_sandboxes,
            )
        except Exception:
            pass

    if sandboxes_dir.is_dir():
        dir_count = len([path for path in sandboxes_dir.iterdir() if path.is_dir()])
        return SandboxStatusInfo(
            active_sandboxes=dir_count,
            total_sandboxes=dir_count,
            max_active_sandboxes=max_active_sandboxes,
        )

    return SandboxStatusInfo(
        active_sandboxes=0,
        total_sandboxes=0,
        max_active_sandboxes=max_active_sandboxes,
    )


def _collect_warnings(
    *,
    git: GitStatusInfo,
    config: ConfigStatusInfo,
    catalog: CatalogStatusInfo,
    sandboxes: SandboxStatusInfo,
) -> list[str]:
    """Aggregate actionable developer warnings in deterministic order."""
    warnings: list[str] = []

    if config.status == ConfigLoadStatus.NOT_FOUND:
        warnings.append("Worktree workspace is not initialized. Run 'wt init' to configure.")

    if git.branch in ("main", "master"):
        warnings.append(f"Active branch is '{git.branch}'. Automated workflows on primary branches are discouraged.")

    if git.is_dirty:
        warnings.append(f"Working tree has {git.uncommitted_files} uncommitted change(s).")

    if config.config is not None and not config.config.agent.model:
        warnings.append("Agent model is not configured (agent.model is null).")

    if sandboxes.max_active_sandboxes > 5:
        warnings.append(f"max_active_sandboxes ({sandboxes.max_active_sandboxes}) is unusually high.")

    if catalog.invalid_items > 0:
        warnings.append(f"{catalog.invalid_items} invalid blueprint file(s) detected in catalog.")

    return warnings


def collect_status(cwd: Path | None = None) -> WorktreeStatusResult:
    """Collect workspace health and runtime status without side effects."""
    root_dir = find_worktree_root(cwd or Path.cwd())

    git_status = _collect_git_status(root_dir)
    config_status = _collect_config_status(root_dir)
    catalog_status = _collect_catalog_status(root_dir)
    database_status = _collect_database_status(root_dir)
    sandbox_status = _collect_sandbox_status(root_dir, config_status, database_status)
    warnings = _collect_warnings(
        git=git_status,
        config=config_status,
        catalog=catalog_status,
        sandboxes=sandbox_status,
    )

    is_initialized = (root_dir / ".worktree").is_dir() and config_status.status != ConfigLoadStatus.NOT_FOUND

    return WorktreeStatusResult(
        root_dir=root_dir,
        is_initialized=is_initialized,
        git=git_status,
        config=config_status,
        catalog=catalog_status,
        database=database_status,
        sandboxes=sandbox_status,
        warnings=warnings,
    )
