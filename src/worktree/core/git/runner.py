"""Stateless Git command execution runner."""

from __future__ import annotations

import subprocess
from pathlib import Path

from worktree.common.constants import GIT_SUBPROCESS_TIMEOUT_SECONDS
from worktree.core.git.exceptions import (
    GitCommandError,
    GitNotFoundError,
    GitPlumbingTimeoutError,
)


class GitRunner:
    """Stateless utility class containing static methods for executing Git commands."""

    @staticmethod
    def run(
        args: list[str],
        path: Path,
        *,
        input_text: str | None = None,
        timeout: int = GIT_SUBPROCESS_TIMEOUT_SECONDS,
        check: bool = True,
    ) -> str:
        """Execute a git command in path and return stripped stdout.

        Args:
            args: Command arguments after ``git``.
            path: Working directory for git command execution.
            input_text: Optional stdin input string.
            timeout: Subprocess timeout in seconds.
            check: When True, raises GitCommandError if returncode != 0.

        Returns:
            Stripped stdout text.

        Raises:
            GitNotFoundError: When git binary is not found.
            GitPlumbingTimeoutError: When subprocess times out.
            GitCommandError: When git command exits non-zero and check is True.
        """
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(path),
                input=input_text,
                capture_output=True,
                text=True,
                check=check,
                timeout=timeout,
            )
            return result.stdout.rstrip("\r\n")
        except FileNotFoundError as exc:
            raise GitNotFoundError(f"Git execution failed ('git {' '.join(args)}'): git not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitPlumbingTimeoutError(
                f"Git timed out after {timeout}s ('git {' '.join(args)}') (GIT_TIMEOUT)"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise GitCommandError(
                cmd=["git", *args],
                returncode=exc.returncode,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            ) from exc

    @staticmethod
    def get_current_branch(path: Path) -> str:
        """Extract current active Git branch, returning 'HEAD (detached)' or 'unknown' on error."""
        try:
            branch = GitRunner.run(["branch", "--show-current"], path=path).strip()
            return branch if branch else "HEAD (detached)"
        except (GitNotFoundError, GitPlumbingTimeoutError, GitCommandError):
            return "unknown"

    @staticmethod
    def status_porcelain(path: Path) -> list[str]:
        """Return raw status porcelain lines for tracked/untracked working tree modifications."""
        try:
            output = GitRunner.run(["status", "--porcelain", "-u"], path=path)
            return [line for line in output.splitlines() if line.strip()]
        except (GitNotFoundError, GitCommandError):
            return []

    @staticmethod
    def worktree_add(
        path: Path,
        target_path: Path,
        branch: str,
        base_ref: str,
    ) -> None:
        """Add a new git worktree with a new branch."""
        GitRunner.run(
            ["worktree", "add", "-b", branch, str(target_path), base_ref],
            path=path,
        )

    @staticmethod
    def worktree_remove(
        path: Path,
        target_path: Path,
        *,
        force: bool = True,
    ) -> None:
        """Remove a git worktree."""
        cmd = ["worktree", "remove", str(target_path)]
        if force:
            cmd.append("--force")
        GitRunner.run(cmd, path=path)

    @staticmethod
    def worktree_prune(path: Path) -> None:
        """Prune stale git worktree administrative records."""
        GitRunner.run(["worktree", "prune"], path=path)

    @staticmethod
    def branch_delete(
        path: Path,
        branch: str,
        *,
        force: bool = True,
    ) -> None:
        """Delete a git branch."""
        flag = "-D" if force else "-d"
        GitRunner.run(["branch", flag, branch], path=path)

    @staticmethod
    def rev_parse(path: Path, rev: str = "HEAD") -> str:
        """Resolve a git revision into a commit SHA."""
        return GitRunner.run(["rev-parse", rev], path=path)

    @staticmethod
    def add_intent_to_add(path: Path, target: str = ".") -> None:
        """Add untracked files to index with intent-to-add flag."""
        try:
            GitRunner.run(["add", "-N", target], path=path)
        except (GitNotFoundError, GitCommandError):
            pass

    @staticmethod
    def diff(
        path: Path,
        base_commit: str,
        *,
        binary: bool = True,
    ) -> str:
        """Generate diff against base_commit."""
        cmd = ["diff"]
        if binary:
            cmd.append("--binary")
        cmd.append(base_commit)
        return GitRunner.run(cmd, path=path)

    @staticmethod
    def diff_name_only(path: Path, base_commit: str) -> list[str]:
        """Return list of modified file paths relative to repository root."""
        output = GitRunner.run(["diff", "--name-only", base_commit], path=path)
        return [line.strip() for line in output.splitlines() if line.strip()]

    @staticmethod
    def diff_stat(path: Path, base_commit: str) -> str:
        """Return diffstat summary against base_commit."""
        return GitRunner.run(["diff", "--stat", base_commit], path=path)

    @staticmethod
    def apply_check(
        path: Path,
        diff_text: str,
        *,
        binary: bool = True,
    ) -> tuple[int, str, str]:
        """Dry-run check whether a patch applies cleanly.

        Returns:
            Tuple of (returncode, stdout, stderr).
        """
        cmd = ["git", "apply", "--check"]
        if binary:
            cmd.append("--binary")
        cmd.append("-")

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(path),
                input=diff_text + "\n",
                capture_output=True,
                text=True,
                timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            raise GitPlumbingTimeoutError(
                f"Git timed out after {GIT_SUBPROCESS_TIMEOUT_SECONDS}s ('git apply --check') (GIT_TIMEOUT)"
            ) from exc
        except FileNotFoundError as exc:
            raise GitNotFoundError("Git execution failed: git not found") from exc

    @staticmethod
    def apply(
        path: Path,
        diff_text: str,
        *,
        binary: bool = True,
    ) -> tuple[int, str, str]:
        """Apply a patch to the working tree.

        Returns:
            Tuple of (returncode, stdout, stderr).
        """
        cmd = ["git", "apply"]
        if binary:
            cmd.append("--binary")
        cmd.append("-")

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(path),
                input=diff_text + "\n",
                capture_output=True,
                text=True,
                timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            raise GitPlumbingTimeoutError(
                f"Git timed out after {GIT_SUBPROCESS_TIMEOUT_SECONDS}s ('git apply') (GIT_TIMEOUT)"
            ) from exc
        except FileNotFoundError as exc:
            raise GitNotFoundError("Git execution failed: git not found") from exc

    @staticmethod
    def add_all(path: Path) -> None:
        """Stage all modifications and untracked files."""
        GitRunner.run(["add", "-A"], path=path)

    @staticmethod
    def commit(path: Path, message: str) -> None:
        """Create a commit with the specified commit message."""
        GitRunner.run(["commit", "-m", message], path=path)
