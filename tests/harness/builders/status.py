"""Fluent status result builder for Worktree CLI test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worktree.common.filesystem import Filesystem
from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.config.models import AgentConfig, ProjectConfig, SandboxConfig, WorktreeConfig
from worktree.core.status.models import (
    CatalogStatusInfo,
    ConfigStatusInfo,
    DatabaseStatusInfo,
    GitStatusInfo,
    SandboxStatusInfo,
    WorktreeStatusResult,
)


class StatusBuilder:
    """Fluent builder for constructing expected WorktreeStatusResult models in tests."""

    def __init__(self, root: Path | None = None) -> None:
        self._root: Path = root or Path("/workspace")
        self._is_initialized: bool = True
        self._git: GitStatusInfo | None = None
        self._config: ConfigStatusInfo | None = None
        self._catalog: CatalogStatusInfo | None = None
        self._database: DatabaseStatusInfo | None = None
        self._sandboxes: SandboxStatusInfo | None = None
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._fixes: list[str] = []

    def with_root(self, root: Path) -> StatusBuilder:
        """Set root workspace directory."""
        self._root = root
        return self

    def with_initialized(self, initialized: bool = True) -> StatusBuilder:
        """Set initialization status flag."""
        self._is_initialized = initialized
        return self

    def with_git(
        self,
        *,
        is_git_repo: bool = True,
        branch: str = "feature-status",
        is_dirty: bool = False,
        uncommitted_files: int = 0,
        status_info: GitStatusInfo | None = None,
    ) -> StatusBuilder:
        """Configure Git repository status info."""
        if status_info is not None:
            self._git = status_info
        else:
            self._git = GitStatusInfo(
                is_git_repo=is_git_repo,
                branch=branch,
                is_dirty=is_dirty,
                uncommitted_files=uncommitted_files,
            )
        return self

    def without_git(self) -> StatusBuilder:
        """Set Git status to indicate non-git repository."""
        self._git = GitStatusInfo(
            is_git_repo=False,
            branch="none",
            is_dirty=False,
            uncommitted_files=0,
        )
        return self

    def with_config(
        self,
        *,
        status: ConfigLoadStatus = ConfigLoadStatus.OK,
        is_valid: bool = True,
        raw: dict[str, Any] | None = None,
        config: WorktreeConfig | None = None,
        errors: list[str] | None = None,
        fixes: list[str] | None = None,
        status_info: ConfigStatusInfo | None = None,
    ) -> StatusBuilder:
        """Configure workspace configuration status info."""
        if status_info is not None:
            self._config = status_info
            return self
        fs = Filesystem(self._root)
        resolved_raw = raw
        if resolved_raw is None and status == ConfigLoadStatus.OK:
            resolved_raw = WorktreeConfig(
                version=1,
                project=ProjectConfig(name="status-ws"),
                agent=AgentConfig(model="gpt-4o"),
                sandbox=SandboxConfig(max_active_sandboxes=5),
            ).model_dump(mode="json")

        resolved_config = config
        if resolved_config is None and resolved_raw is not None:
            resolved_config = WorktreeConfig.model_validate(resolved_raw)

        self._config = ConfigStatusInfo(
            status=status,
            config_path=fs.config_file,
            is_valid=is_valid,
            raw=resolved_raw,
            config=resolved_config,
            errors=errors if errors is not None else [],
            fixes=fixes if fixes is not None else [],
        )
        return self

    def without_config(
        self,
        *,
        errors: list[str] | None = None,
        fixes: list[str] | None = None,
    ) -> StatusBuilder:
        """Set configuration status to indicate uninitialized missing configuration."""
        fs = Filesystem(self._root)
        self._is_initialized = False
        default_errors = [f"Configuration file not found at '{fs.config_file}' (CONFIG_NOT_FOUND)."]
        default_fixes = ["Run `wt init` to create `.worktree/config.json`"]
        self._config = ConfigStatusInfo(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=fs.config_file,
            is_valid=False,
            raw=None,
            config=None,
            errors=errors if errors is not None else default_errors,
            fixes=fixes if fixes is not None else default_fixes,
        )
        return self

    def with_catalog(
        self,
        *,
        exists: bool = True,
        total_items: int = 0,
        workflows_count: int = 0,
        tasks_count: int = 0,
        steps_count: int = 0,
        invalid_items: int = 0,
        item_names: list[str] | None = None,
        status_info: CatalogStatusInfo | None = None,
    ) -> StatusBuilder:
        """Configure blueprint catalog status info."""
        if status_info is not None:
            self._catalog = status_info
        else:
            self._catalog = CatalogStatusInfo(
                exists=exists,
                catalog_dir=Filesystem(self._root).catalog_dir,
                total_items=total_items,
                workflows_count=workflows_count,
                tasks_count=tasks_count,
                steps_count=steps_count,
                invalid_items=invalid_items,
                item_names=item_names if item_names is not None else [],
            )
        return self

    def with_database(
        self,
        *,
        exists: bool = True,
        is_accessible: bool = True,
        total_runs: int = 0,
        status_info: DatabaseStatusInfo | None = None,
    ) -> StatusBuilder:
        """Configure SQLite database status info."""
        if status_info is not None:
            self._database = status_info
        else:
            self._database = DatabaseStatusInfo(
                exists=exists,
                db_path=Filesystem(self._root).db_file,
                is_accessible=is_accessible,
                total_runs=total_runs,
            )
        return self

    def without_database(self) -> StatusBuilder:
        """Set database status to indicate missing database."""
        self._database = DatabaseStatusInfo(
            exists=False,
            db_path=Filesystem(self._root).db_file,
            is_accessible=False,
            total_runs=0,
        )
        return self

    def with_sandboxes(
        self,
        *,
        active_sandboxes: int = 0,
        total_sandboxes: int = 0,
        max_active_sandboxes: int = 5,
        status_info: SandboxStatusInfo | None = None,
    ) -> StatusBuilder:
        """Configure active and total sandbox status info."""
        if status_info is not None:
            self._sandboxes = status_info
        else:
            self._sandboxes = SandboxStatusInfo(
                active_sandboxes=active_sandboxes,
                total_sandboxes=total_sandboxes,
                max_active_sandboxes=max_active_sandboxes,
            )
        return self

    def with_warnings(self, *warnings: str) -> StatusBuilder:
        """Append expected warning messages."""
        self._warnings.extend(warnings)
        return self

    def with_fixes(self, *fixes: str) -> StatusBuilder:
        """Append expected remediation fix messages."""
        self._fixes.extend(fixes)
        return self

    def with_errors(self, *errors: str) -> StatusBuilder:
        """Append expected error messages."""
        self._errors.extend(errors)
        return self

    def build(self) -> WorktreeStatusResult:
        """Assemble and return the complete WorktreeStatusResult."""
        fs = Filesystem(self._root)
        git = self._git or GitStatusInfo(
            is_git_repo=True,
            branch="feature-status",
            is_dirty=False,
            uncommitted_files=0,
        )

        if self._config is not None:
            config = self._config
        else:
            raw = WorktreeConfig(
                version=1,
                project=ProjectConfig(name="status-ws"),
                agent=AgentConfig(model="gpt-4o"),
                sandbox=SandboxConfig(max_active_sandboxes=5),
            ).model_dump(mode="json")
            config = ConfigStatusInfo(
                status=ConfigLoadStatus.OK,
                config_path=fs.config_file,
                is_valid=True,
                raw=raw,
                config=WorktreeConfig.model_validate(raw),
                errors=[],
                fixes=[],
            )

        catalog = self._catalog or CatalogStatusInfo(
            exists=False,
            catalog_dir=fs.catalog_dir,
            total_items=0,
            workflows_count=0,
            tasks_count=0,
            steps_count=0,
            invalid_items=0,
            item_names=[],
        )

        database = self._database or DatabaseStatusInfo(
            exists=True,
            db_path=fs.db_file,
            is_accessible=True,
            total_runs=0,
        )

        sandboxes = self._sandboxes or SandboxStatusInfo(
            active_sandboxes=0,
            total_sandboxes=0,
            max_active_sandboxes=5,
        )

        return WorktreeStatusResult(
            root_dir=self._root,
            is_initialized=self._is_initialized,
            git=git,
            config=config,
            catalog=catalog,
            database=database,
            sandboxes=sandboxes,
            errors=list(self._errors),
            warnings=list(self._warnings),
            fixes=list(self._fixes),
        )
