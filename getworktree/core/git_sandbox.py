"""getworktree/core/git_sandbox.py.

Orchestrates native Git worktree operations to spawn isolated background directories
where agent execution loops run safely without polluting uncommitted working tree changes.
"""

import shutil
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from getworktree.core.config_manager import load_context

console = Console()


@dataclass
class SandboxSession:
    """Metadata for one isolated background git worktree."""

    session_id: str
    target_branch: str
    sandbox_path: Path
    created_at: str


class GitSandboxManager:
    """Manages creation, execution context, and pruning of background Git worktrees."""

    def __init__(self, cwd: Path | None = None):
        """Bind to a repository root and load workspace context."""
        self.cwd = (cwd or Path.cwd()).resolve()
        # Hook into Issue #3: Load workspace context and config settings
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
        """Spawn an isolated background git worktree targeting a dynamic branch.

        Enforces `max_background_runs` bounds loaded from config_manager.
        """
        self._ensure_sandbox_dir()

        # Enforce execution limits from Issue #3 config
        active_sandboxes = self.get_active_sandboxes()
        max_allowed = self.context.config.sandbox.max_active_sandboxes
        if len(active_sandboxes) >= max_allowed:
            raise RuntimeError(
                f"Maximum active background sandboxes reached ({len(active_sandboxes)}/{max_allowed}). "
                "Prune existing sandboxes or adjust 'sandbox.max_active_sandboxes' in .worktree/config.json."
            )

        sid = session_id or f"sbx_{uuid.uuid4().hex[:8]}"
        sandbox_path = self.sandbox_base_dir / sid
        temp_branch = f"worktree/sandbox-{sid}"

        # Execute native git worktree creation
        # git worktree add -b <temp_branch> <path> <source_branch>
        source_branch = self.context.current_branch
        self._run_git_cmd(
            [
                "worktree",
                "add",
                "-b",
                temp_branch,
                str(sandbox_path),
                source_branch if source_branch != "unknown" else "HEAD",
            ]
        )

        session = SandboxSession(
            session_id=sid,
            target_branch=temp_branch,
            sandbox_path=sandbox_path,
            created_at=datetime.now(UTC).isoformat(),
        )

        console.print(
            f"[bold green]✔ Spawned isolated sandbox:[/bold green] [cyan]{sandbox_path.relative_to(self.cwd)}[/cyan] "
            f"([dim]Branch: {temp_branch}[/dim])"
        )
        return session

    def cleanup_sandbox(self, session: SandboxSession, force: bool = True) -> None:
        """Detach git worktree, remove sandbox directory, and delete temporary branch.

        Runs `git worktree prune` when finished.
        """
        if session.sandbox_path.exists():
            # 1. Remove git worktree link
            cmd = ["worktree", "remove", str(session.sandbox_path)]
            if force:
                cmd.append("--force")
            try:
                self._run_git_cmd(cmd)
            except RuntimeError:
                # Fallback to direct directory removal if worktree command fails
                shutil.rmtree(session.sandbox_path, ignore_errors=True)

        # 2. Delete temporary branch spawned for the sandbox
        try:
            self._run_git_cmd(["branch", "-D", session.target_branch])
        except RuntimeError:
            pass  # Branch may already be deleted or not checked out

        # 3. Clean stale worktree references
        self.prune()

        console.print(
            f"[dim]• Cleaned up background sandbox: {session.session_id}[/dim]"
        )

    def prune(self) -> None:
        """Prune all stale Git worktrees."""
        self._run_git_cmd(["worktree", "prune"])


@contextmanager
def sandbox_scope(cwd: Path | None = None, session_id: str | None = None):
    """Context manager for sandbox execution with optional auto-cleanup.

    Teardown respects the workspace `auto_clean` setting.
    """
    manager = GitSandboxManager(cwd=cwd)
    session = manager.create_sandbox(session_id=session_id)
    try:
        yield session
    finally:
        # Respect auto_clean setting from Issue #3 config_manager
        if manager.context.config.sandbox.auto_clean:
            manager.cleanup_sandbox(session)
