"""Fluent workspace data builder for Worktree CLI test suite."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from worktree.common.filesystem import Filesystem
from worktree.core.bootstrap.services.bootstrap import bootstrap_worktree
from worktree.core.catalog.services.seeder import seed_all_catalog_templates
from worktree.core.config.generator import generate_default_config
from worktree.core.db.connection import DEFAULT_DB_REL_PATH
from worktree.core.db.migrations import init_database


class WorkspaceBuilder:
    """Fluent builder for scaffolding test workspaces on the filesystem."""

    def __init__(self, root: Path | None = None) -> None:
        self._root: Path | None = root
        self._project_name: str | None = None
        self._scaffold_config: bool = True
        self._config_overwrite: bool = True
        self._scaffold_database: bool = True
        self._scaffold_catalog: bool = True
        self._catalog_force: bool = True
        self._init_git: bool = False
        self._config_data: dict[str, Any] | None = None
        self._db_rel_path: str = DEFAULT_DB_REL_PATH
        self._git_branch: str = "main"
        self._git_user_name: str = "Test User"
        self._git_user_email: str = "test@example.com"

    def with_project_name(self, name: str) -> WorkspaceBuilder:
        """Set project name for generated configuration."""
        self._project_name = name
        return self

    def with_config(
        self,
        *,
        data: dict[str, Any] | None = None,
        overwrite: bool = True,
    ) -> WorkspaceBuilder:
        """Enable config generation with optional explicit payload."""
        self._scaffold_config = True
        self._config_data = data
        self._config_overwrite = overwrite
        return self

    def without_config(self) -> WorkspaceBuilder:
        """Disable config.json generation."""
        self._scaffold_config = False
        return self

    def with_database(self, db_rel_path: str = DEFAULT_DB_REL_PATH) -> WorkspaceBuilder:
        """Enable SQLite database migration."""
        self._scaffold_database = True
        self._db_rel_path = db_rel_path
        return self

    def without_database(self) -> WorkspaceBuilder:
        """Disable SQLite database creation."""
        self._scaffold_database = False
        return self

    def with_catalog_templates(self, *, force: bool = True) -> WorkspaceBuilder:
        """Enable catalog templates seeding."""
        self._scaffold_catalog = True
        self._catalog_force = force
        return self

    def without_catalog_templates(self) -> WorkspaceBuilder:
        """Disable catalog templates seeding."""
        self._scaffold_catalog = False
        return self

    def with_git(
        self,
        *,
        branch: str = "main",
        user_name: str = "Test User",
        user_email: str = "test@example.com",
    ) -> WorkspaceBuilder:
        """Enable Git repository initialization."""
        self._init_git = True
        self._git_branch = branch
        self._git_user_name = user_name
        self._git_user_email = user_email
        return self

    def build(self) -> Path:
        """Scaffold and return the prepared workspace directory root."""
        if self._root is not None:
            workspace_root = self._root.resolve()
            workspace_root.mkdir(parents=True, exist_ok=True)
        else:
            workspace_root = Path(tempfile.mkdtemp(prefix="wt_workspace_")).resolve()

        dot_worktree = workspace_root / ".worktree"
        dot_worktree.mkdir(parents=True, exist_ok=True)
        bootstrap_worktree(dot_worktree)

        (dot_worktree / "sandboxes").mkdir(parents=True, exist_ok=True)

        if self._init_git:
            self._scaffold_git_repository(workspace_root)

        if self._scaffold_config:
            self._scaffold_workspace_config(workspace_root, dot_worktree)

        if self._scaffold_database:
            init_database(workspace_root, db_rel_path=self._db_rel_path)

        if self._scaffold_catalog:
            seed_all_catalog_templates(workspace_root, force=self._catalog_force)

        return workspace_root

    def _scaffold_git_repository(self, workspace_root: Path) -> None:
        subprocess.run(
            ["git", "init", "-b", self._git_branch],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", self._git_user_name],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.email", self._git_user_email],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )

        readme_path = workspace_root / "README.md"
        if not readme_path.exists():
            readme_path.write_text("# Test Repo\n", encoding="utf-8")

        gitignore_path = workspace_root / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text("/.worktree/\n", encoding="utf-8")

        subprocess.run(
            ["git", "add", "README.md", ".gitignore"],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )

    def _scaffold_workspace_config(self, workspace_root: Path, dot_worktree: Path) -> None:
        config_path = dot_worktree / "config.json"
        if self._config_data is not None:
            if not self._config_overwrite and config_path.exists():
                return
            Filesystem.atomic_write_json(config_path, self._config_data)
        else:
            project_name = self._project_name or workspace_root.name
            generate_default_config(config_path, project_name=project_name, overwrite=self._config_overwrite)
