"""Filesystem bootstrap for the local Worktree home directory (`.worktree/`).

Symlink policy: the `.worktree` root may be a symlink to a directory; required
subdirectories must be real directories (not symlinks).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from worktree.common.constants import (
    BOOTSTRAP_META_REL,
    BOOTSTRAP_SCHEMA_VERSION,
    REQUIRED_SUBDIRS,
)
from worktree.common.fs import (
    atomic_write_json,
    get_gitignore_file,
    get_worktree_config_file,
    get_worktree_dir,
    is_git_repository,
    update_gitignore,
)
from worktree.common.utils import display_path
from worktree.core.catalog.models import SeedResult
from worktree.core.catalog.services.seeder import seed_all_catalog_templates
from worktree.core.config.generator import ConfigGenerationResult, generate_default_config
from worktree.core.config.loader import load_config_result
from worktree.core.config.models import PathsConfig
from worktree.core.db import init_database


class DirEnsureOutcome(Enum):
    """Result of attempting to ensure a directory exists."""

    CREATED = "created"
    EXISTING = "existing"


class BootstrapResult(BaseModel):
    """Outcome of bootstrapping the `.worktree/` directory tree."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    root_path: Path
    root_created: bool = False
    dirs_created: list[Path] = Field(default_factory=list)
    dirs_existing: list[Path] = Field(default_factory=list)
    repaired: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    seed_result: SeedResult = Field(default_factory=SeedResult)

    @property
    def ok(self) -> bool:
        """True when bootstrap completed without errors."""
        return not self.errors


class WorkspaceInitResult(BaseModel):
    """Structured outcome of initializing a project workspace."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    bootstrap_result: BootstrapResult | None = None
    config_result: ConfigGenerationResult | None = None
    seed_result: SeedResult | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when bootstrap, config, and catalog seeding all succeed with no errors."""
        return (
            not self.errors
            and self.bootstrap_result is not None
            and self.bootstrap_result.ok
            and self.config_result is not None
            and self.config_result.ok
            and self.seed_result is not None
            and self.seed_result.ok
        )


def _validate_existing_dir(path: Path, *, allow_symlink: bool) -> None:
    """Raise ValueError when an existing path is not a usable directory."""
    if path.is_symlink():
        if allow_symlink:
            if not path.is_dir():
                raise ValueError(f"{display_path(path)} is a symlink that does not resolve to a directory.")
            return
        raise ValueError(f"{display_path(path)} must be a directory, not a symlink.")
    if path.is_file():
        raise ValueError(f"{display_path(path)} exists but is a file, not a directory.")
    if not path.is_dir():
        raise ValueError(f"{display_path(path)} is not a usable directory.")


def ensure_dir(path: Path, *, allow_symlink: bool = False) -> DirEnsureOutcome:
    """Create a directory if missing.

    Raises ValueError with an actionable message when the path is invalid.
    """
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(
                f"Could not create {display_path(path)}: {exc}. Check directory permissions and try again."
            ) from exc
        return DirEnsureOutcome.CREATED

    _validate_existing_dir(path, allow_symlink=allow_symlink)
    return DirEnsureOutcome.EXISTING


def assert_writable(path: Path) -> None:
    """Verify that an existing path is writable."""
    if not path.exists():
        raise ValueError(f"{display_path(path)} does not exist.")
    if not os.access(path, os.W_OK):
        raise ValueError(f"{display_path(path)} is not writable. Check directory permissions and try again.")


def load_existing_bootstrap_metadata(meta_path: Path) -> dict[str, object] | None:
    """Load `.meta/bootstrap.json` if present and valid."""
    if not meta_path.is_file():
        return None
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def write_bootstrap_metadata(
    meta_path: Path,
    *,
    root_path: Path,
    status: str,
    tool_version: str | None,
    initialized_at: str | None,
) -> None:
    """Write bootstrap metadata for diagnostics and idempotent init."""
    now = datetime.now(UTC).isoformat()
    payload: dict[str, object] = {
        "schema_version": BOOTSTRAP_SCHEMA_VERSION,
        "initialized_at": initialized_at or now,
        "last_checked_at": now,
        "tool_version": tool_version,
        "status": status,
        "root_path": str(root_path),
    }
    atomic_write_json(meta_path, payload)


def _ensure_required_subdirs(root_path: Path, result: BootstrapResult) -> bool:
    """Ensure REQUIRED_SUBDIRS under root_path. Returns False when a path error is recorded."""
    for name in REQUIRED_SUBDIRS:
        sub_path = root_path / name
        try:
            outcome = ensure_dir(sub_path, allow_symlink=False)
        except ValueError as exc:
            result.errors.append(str(exc))
            return False
        if outcome == DirEnsureOutcome.CREATED:
            result.dirs_created.append(sub_path)
        else:
            result.dirs_existing.append(sub_path)
    return True


def _assert_layout_writable(root_path: Path, result: BootstrapResult) -> bool:
    """Assert root and known subdirs are writable. Returns False when a path error is recorded."""
    try:
        assert_writable(root_path)
        for sub_path in result.dirs_created + result.dirs_existing:
            assert_writable(sub_path)
    except ValueError as exc:
        result.errors.append(str(exc))
        return False
    return True


def _bootstrap_status(
    *,
    repaired: bool,
    root_created: bool,
    dirs_created: list[Path],
    prior_meta: dict[str, object] | None,
) -> str:
    if repaired:
        return "repaired"
    if root_created or dirs_created:
        return "initialized"
    if prior_meta:
        return str(prior_meta.get("status", "initialized"))
    return "initialized"


def bootstrap_worktree(
    root_path: Path,
    *,
    tool_version: str | None = None,
) -> BootstrapResult:
    """Create and validate the Worktree home layout under ``root_path`` (typically ``.worktree``).

    Idempotent: safe to run multiple times; never deletes user data.
    """
    root_path = root_path.resolve()
    result = BootstrapResult(root_path=root_path)
    meta_path = root_path / BOOTSTRAP_META_REL
    prior_meta = load_existing_bootstrap_metadata(meta_path)

    try:
        root_outcome = _ensure_worktree_root(root_path)
        result.root_created = root_outcome == DirEnsureOutcome.CREATED
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    if not result.root_created:
        try:
            assert_writable(root_path)
        except ValueError as exc:
            result.errors.append(str(exc))
            return result

    if not _ensure_required_subdirs(root_path, result):
        return result
    if not _assert_layout_writable(root_path, result):
        return result

    result.repaired = _is_repair(
        root_created=result.root_created,
        dirs_created=result.dirs_created,
        dirs_existing=result.dirs_existing,
        prior_meta=prior_meta,
    )
    if result.errors:
        return result

    status = _bootstrap_status(
        repaired=result.repaired,
        root_created=result.root_created,
        dirs_created=result.dirs_created,
        prior_meta=prior_meta,
    )
    initialized_at = str(prior_meta["initialized_at"]) if prior_meta and prior_meta.get("initialized_at") else None

    try:
        write_bootstrap_metadata(
            meta_path,
            root_path=root_path,
            status=status,
            tool_version=tool_version,
            initialized_at=initialized_at,
        )
    except OSError as exc:
        result.errors.append(f"Could not write bootstrap metadata at {display_path(meta_path)}: {exc}")

    result.seed_result = SeedResult()
    return result


def _is_repair(
    *,
    root_created: bool,
    dirs_created: list[Path],
    dirs_existing: list[Path],
    prior_meta: dict[str, object] | None,
) -> bool:
    """True when missing pieces were added to an already-present worktree layout."""
    if not dirs_created:
        return False
    # Partial tree, re-init after prior bootstrap, or root already existed.
    return bool(dirs_existing) or prior_meta is not None or not root_created


def _ensure_worktree_root(root_path: Path) -> DirEnsureOutcome:
    return ensure_dir(root_path, allow_symlink=True)


def initialize_workspace(
    root: Path,
    *,
    tool_version: str | None = None,
    overwrite: bool = False,
    repair: bool = False,
) -> WorkspaceInitResult:
    """Initialize a local project workspace for Worktree CLI and desktop sync.

    Performs git preflight, bootstraps the `.worktree/` directory tree, updates
    `.gitignore`, generates canonical default configuration, initializes the SQLite
    state database, and seeds starter catalog templates.
    """
    root = root.resolve()

    if not is_git_repository(root):
        err = (
            "The current directory is not a valid Git repository.\n"
            "Run [bold cyan]git init[/bold cyan] before running [bold cyan]wt init[/bold cyan]."
        )
        return WorkspaceInitResult(errors=[err])

    result = bootstrap_worktree(get_worktree_dir(root), tool_version=tool_version)
    if not result.ok:
        return WorkspaceInitResult(bootstrap_result=result, errors=list(result.errors))

    if result.root_created:
        update_gitignore(get_gitignore_file(root))

    config_result = generate_default_config(
        get_worktree_config_file(root),
        project_name=root.name,
        overwrite=overwrite,
        repair=repair,
    )
    if not config_result.ok:
        return WorkspaceInitResult(
            bootstrap_result=result,
            config_result=config_result,
            errors=list(config_result.errors),
        )

    db_rel = PathsConfig().db_path
    loaded = load_config_result(path=root)
    if loaded.ok and loaded.config is not None:
        db_rel = loaded.config.paths.db_path
    init_database(path=root, db_rel_path=db_rel)

    seed_result = seed_all_catalog_templates(path=root)
    return WorkspaceInitResult(
        bootstrap_result=result,
        config_result=config_result,
        seed_result=seed_result,
        errors=list(seed_result.errors),
    )
