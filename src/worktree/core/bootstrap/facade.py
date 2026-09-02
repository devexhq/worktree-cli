"""Bootstrap domain facade."""

from __future__ import annotations

from pathlib import Path

from worktree.common.filesystem import Filesystem
from worktree.core.bootstrap.models import BootstrapResult, WorkspaceInitResult
from worktree.core.bootstrap.services.bootstrap import bootstrap_worktree
from worktree.core.bootstrap.services.initialize import initialize_workspace


class Bootstrap:
    """Unified entrypoint for worktree directory bootstrapping and workspace initialization."""

    def __init__(self, path: Path = Path(".")) -> None:
        self.path = path.resolve()

    def bootstrap(self, *, tool_version: str | None = None) -> BootstrapResult:
        """Bootstrap the .worktree/ directory structure at self.path."""
        worktree_dir = Filesystem(self.path).worktree_dir
        return bootstrap_worktree(worktree_dir, tool_version=tool_version)

    def initialize(
        self,
        *,
        tool_version: str | None = None,
        overwrite: bool = False,
        repair: bool = False,
    ) -> WorkspaceInitResult:
        """Initialize the project workspace at self.path."""
        return initialize_workspace(
            self.path,
            tool_version=tool_version,
            overwrite=overwrite,
            repair=repair,
        )
