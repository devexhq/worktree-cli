"""Unified coordinator facade for Git worktree sandboxes."""

from __future__ import annotations

from pathlib import Path

from worktree.common.lock import WorkspaceLock
from worktree.core.config.models import WorktreeConfig
from worktree.core.db import RunsRepository, SandboxesRepository, SandboxRecord
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxApplyStrategy,
    SandboxCreateResult,
    SandboxDetectionResult,
    SandboxDiffResult,
    SandboxSession,
)
from worktree.core.sandbox.services.detector import SandboxDetector
from worktree.core.sandbox.services.lifecycle import SandboxLifecycle
from worktree.core.sandbox.services.patch import SandboxPatch


class GitSandboxManager:
    """Coordinator facade orchestrating sandbox lifecycle and patch services."""

    def __init__(self, path: Path, db: SandboxesRepository) -> None:
        """Bind to repository root with an explicit database repository.

        Args:
            path: Repository root directory.
            db: Explicit SandboxesRepository instance.
        """
        self.path = path.expanduser().resolve()
        self.db = db
        self.lifecycle = SandboxLifecycle(self.path, self.db)
        self.patch = SandboxPatch(self.path, self.db, lifecycle=self.lifecycle)

    @property
    def config(self) -> WorktreeConfig | None:
        """Return the config last loaded by a successful create attempt."""
        return self.lifecycle.config

    @property
    def sandbox_base_dir(self) -> Path:
        """Base storage directory for created sandboxes."""
        return self.lifecycle.sandbox_base_dir

    def create_sandbox(
        self,
        session_id: str | None = None,
        *,
        include_wip: bool = False,
        name: str | None = None,
        base_ref: str | None = None,
    ) -> SandboxCreateResult:
        """Create an isolated sandbox worktree and return structured result."""
        with WorkspaceLock(self.path):
            return self.lifecycle.create(
                session_id=session_id,
                include_wip=include_wip,
                name=name,
                base_ref=base_ref,
            )

    def cleanup_sandbox(
        self,
        session: SandboxSession | SandboxRecord,
        *,
        force: bool = True,
    ) -> list[str]:
        """Remove worktree, delete throwaway branch, and prune."""
        with WorkspaceLock(self.path):
            return self.lifecycle.cleanup(session, force=force)

    def prune(self) -> None:
        """Prune stale Git worktree registrations."""
        with WorkspaceLock(self.path):
            self.lifecycle.prune()

    def get_active_sandboxes(self) -> list[Path]:
        """List active sandbox directories."""
        return self.lifecycle.get_active()

    def apply_sandbox(
        self,
        sandbox_id: str,
        *,
        strategy: SandboxApplyStrategy = SandboxApplyStrategy.PATCH,
        allow_dirty: bool = False,
        dry_run: bool = False,
        delete: bool = False,
        message: str | None = None,
    ) -> SandboxApplyResult:
        """Apply sandbox changes back to main workspace."""
        with WorkspaceLock(self.path):
            return self.patch.apply(
                sandbox_id=sandbox_id,
                strategy=strategy,
                allow_dirty=allow_dirty,
                dry_run=dry_run,
                delete=delete,
                message=message,
            )

    def diff_sandbox(
        self,
        sandbox_id: str,
        *,
        stat: bool = False,
    ) -> SandboxDiffResult:
        """Inspect unified diff or diffstat for a sandbox."""
        return self.patch.diff(sandbox_id=sandbox_id, stat=stat)

    def detect_stale_sandboxes(
        self,
        runs_db: RunsRepository | None = None,
    ) -> SandboxDetectionResult:
        """Scan repository for stale sandboxes, orphaned directories, and dead refs."""
        detector = SandboxDetector(self.path, self.db, runs_db=runs_db)
        return detector.detect()
