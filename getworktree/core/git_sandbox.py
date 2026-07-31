"""Orchestrate native Git worktree sandboxes for isolated command execution."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from getworktree.core.config.context import load_context


class SandboxSession(BaseModel):
    """Metadata for one isolated background git worktree."""

    model_config = {"extra": "forbid", "strict": True}

    session_id: str
    target_branch: str
    sandbox_path: Path
    created_at: str
    command_passed: bool | None = None


class GitSandboxManager:
    """Manages creation, execution context, and pruning of background Git worktrees."""

    def __init__(self, cwd: Path | None = None):
        """Bind to a repository root and load workspace context."""
        self.cwd = (cwd or Path.cwd()).resolve()
        self.context = load_context(self.cwd)
        self.sandbox_base_dir = self.cwd / ".worktree" / "sandboxes"

    def _ensure_sandbox_dir(self) -> None:
        """Create the parent sandbox storage directory if missing."""
        self.sandbox_base_dir.mkdir(parents=True, exist_ok=True)

    def _run_git_cmd(self, args: list[str], cwd: Path | None = None) -> str:
        """Execute git command wrapped in standard subprocess calls."""
        target_dir = cwd or self.cwd
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() or e.stdout.strip()
            raise RuntimeError(
                f"Git execution failed ('git {' '.join(args)}'): {err_msg}"
            ) from e

    def get_active_sandboxes(self) -> list[Path]:
        """List current background sandbox directories on disk."""
        if not self.sandbox_base_dir.exists():
            return []
        return [p for p in self.sandbox_base_dir.iterdir() if p.is_dir()]

    def create_sandbox(self, session_id: str | None = None) -> SandboxSession:
        """Spawn an isolated background git worktree targeting a dynamic branch."""
        self._ensure_sandbox_dir()

        active_sandboxes = self.get_active_sandboxes()
        max_allowed = self.context.config.sandbox.max_active_sandboxes
        if len(active_sandboxes) >= max_allowed:
            raise RuntimeError(
                f"Maximum active background sandboxes reached "
                f"({len(active_sandboxes)}/{max_allowed}). "
                "Prune existing sandboxes or adjust "
                "'sandbox.max_active_sandboxes' in .worktree/config.json."
            )

        sid = session_id or f"sbx_{uuid.uuid4().hex[:8]}"
        sandbox_path = self.sandbox_base_dir / sid
        temp_branch = f"worktree/sandbox-{sid}"

        source_branch = self.context.current_branch
        base_ref = (
            source_branch
            if source_branch not in ("unknown", "HEAD (detached)")
            else self.context.config.sandbox.base_ref
        )
        self._run_git_cmd(
            [
                "worktree",
                "add",
                "-b",
                temp_branch,
                str(sandbox_path),
                base_ref,
            ]
        )

        return SandboxSession(
            session_id=sid,
            target_branch=temp_branch,
            sandbox_path=sandbox_path,
            created_at=datetime.now(UTC).isoformat(),
        )

    def cleanup_sandbox(self, session: SandboxSession, force: bool = True) -> None:
        """Detach git worktree, remove sandbox directory, and delete temporary branch."""
        if session.sandbox_path.exists():
            cmd = ["worktree", "remove", str(session.sandbox_path)]
            if force:
                cmd.append("--force")
            try:
                self._run_git_cmd(cmd)
            except RuntimeError:
                shutil.rmtree(session.sandbox_path, ignore_errors=True)

        try:
            self._run_git_cmd(["branch", "-D", session.target_branch])
        except RuntimeError:
            pass

        self.prune()

    def prune(self) -> None:
        """Prune all stale Git worktrees."""
        self._run_git_cmd(["worktree", "prune"])


@contextmanager
def sandbox_scope(
    cwd: Path | None = None, session_id: str | None = None
) -> Generator[SandboxSession]:
    """Context manager for sandbox execution with optional auto-cleanup.

    Teardown respects ``auto_clean`` and ``keep_on_failure`` sandbox settings.
    """
    manager = GitSandboxManager(cwd=cwd)
    session = manager.create_sandbox(session_id=session_id)
    try:
        yield session
    finally:
        sandbox_cfg = manager.context.config.sandbox
        should_clean = sandbox_cfg.auto_clean
        failed = session.command_passed is False
        if failed and sandbox_cfg.keep_on_failure:
            should_clean = False
        if should_clean:
            manager.cleanup_sandbox(session)
