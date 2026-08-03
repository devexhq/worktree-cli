"""Orchestrate native Git worktree sandboxes for isolated command execution."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from getworktree.core.config.context import get_current_git_branch
from getworktree.core.config.loader import ConfigLoadStatus, load_config_result
from getworktree.core.config.models import WorktreeConfig


class SandboxSession(BaseModel):
    """Metadata for one isolated background git worktree."""

    model_config = {"extra": "forbid", "strict": True}

    session_id: str
    target_branch: str
    sandbox_path: Path
    created_at: str
    command_passed: bool | None = None
    wip_applied: bool = False
    wip_paths: list[str] = Field(default_factory=list)


class SandboxCreateStatus(StrEnum):
    """Classified outcomes for creating a sandbox worktree."""

    OK = "ok"
    CAPACITY_EXCEEDED = "capacity_exceeded"
    GIT_FAILED = "git_failed"
    NOT_INITIALIZED = "not_initialized"
    UNREADABLE_CONFIG = "unreadable_config"
    WIP_FAILED = "wip_failed"


class SandboxCreateResult(BaseModel):
    """Non-raising result of sandbox creation."""

    model_config = {"extra": "forbid", "strict": True}

    status: SandboxCreateStatus
    session: SandboxSession | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when a sandbox session was created successfully."""
        return self.status == SandboxCreateStatus.OK and not self.errors


def should_cleanup_sandbox(
    *,
    auto_clean: bool,
    keep_on_failure: bool,
    command_passed: bool | None,
) -> bool:
    """Return whether a sandbox should be removed after a run.

    Args:
        auto_clean: When False, never clean up.
        keep_on_failure: When True with auto_clean, retain sandboxes after failure.
        command_passed: Run outcome; None means unclassified (still clean when
            auto_clean is True).

    Returns:
        True when cleanup should run.
    """
    if not auto_clean:
        return False
    if keep_on_failure and command_passed is False:
        return False
    return True


def _capacity_error(active: int, max_allowed: int) -> str:
    return (
        f"Maximum active sandboxes reached ({active}/{max_allowed}).\n"
        "Fix:\n"
        "- run `wt prune` to remove stale sandboxes, or\n"
        "- raise sandbox.max_active_sandboxes in .worktree/config.json"
    )


def _not_initialized_error(config_path: Path) -> str:
    return (
        f"Worktree is not initialized; config missing at '{config_path}' "
        f"(SANDBOX_NOT_INITIALIZED).\n"
        "Fix:\n"
        "- run `wt init` to create `.worktree/config.json`"
    )


def _unreadable_config_error(detail: str) -> str:
    return (
        f"Unable to load Worktree config for sandbox create "
        f"(SANDBOX_CONFIG_UNREADABLE): {detail}\n"
        "Fix:\n"
        "- repair `.worktree/config.json` or run `wt init --repair`"
    )


def _git_failed_error(detail: str) -> str:
    return (
        f"Git worktree operation failed (SANDBOX_GIT_FAILED): {detail}\n"
        "Fix:\n"
        "- ensure this directory is a Git repository with a valid base ref"
    )


def _wip_failed_error(detail: str) -> str:
    return (
        f"Failed to overlay uncommitted WIP into sandbox "
        f"(SANDBOX_WIP_FAILED): {detail}\n"
        "Fix:\n"
        "- resolve local conflicts / binary issues and retry, or\n"
        "- omit --wip and commit changes first"
    )


def _normalize_repo_rel(path: str) -> str:
    return path.strip().replace("\\", "/")


def _list_wip_paths(repo_root: Path) -> list[str]:
    """Return sorted repo-relative paths with uncommitted changes.

    Includes tracked modifications/deletions and untracked non-ignored files.
    """
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain", "-u"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    paths: set[str] = set()
    for raw in completed.stdout.splitlines():
        if len(raw) < 4:
            continue
        entry = raw[3:]
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip().strip('"')
        rel = _normalize_repo_rel(entry)
        if rel:
            paths.add(rel)
    return sorted(paths)


def _copy_wip_file(source_root: Path, dest_root: Path, rel: str) -> None:
    src = source_root / rel
    dst = dest_root / rel
    if not src.exists():
        if dst.exists() or dst.is_symlink():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        return
    if src.is_dir() and not src.is_symlink():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        if dst.exists() or dst.is_symlink():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.symlink_to(src.readlink())
        return
    shutil.copy2(src, dst)


def apply_wip_to_sandbox(*, source_root: Path, sandbox_path: Path) -> list[str]:
    """Overlay uncommitted working-tree changes into an existing sandbox.

    Copies tracked and untracked (non-ignored) paths from ``source_root`` into
    ``sandbox_path``. Deleted tracked files are removed in the sandbox.

    Args:
        source_root: Primary repository checkout (WIP source).
        sandbox_path: Sandbox worktree path.

    Returns:
        Sorted list of repo-relative paths touched by the overlay.

    Raises:
        RuntimeError: When overlay fails.
    """
    root = source_root.expanduser().resolve()
    dest = sandbox_path.expanduser().resolve()
    if not dest.is_dir():
        raise RuntimeError(f"sandbox path does not exist: {dest}")

    paths = _list_wip_paths(root)
    try:
        for rel in paths:
            _copy_wip_file(root, dest, rel)
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
    return paths


class GitSandboxManager:
    """Manages creation, cleanup, and pruning of background Git worktrees."""

    def __init__(self, cwd: Path | None = None) -> None:
        """Bind to an absolute repository root.

        Args:
            cwd: Repository root. Defaults to the process current directory.
        """
        self.cwd = (cwd or Path.cwd()).expanduser().resolve()
        self.sandbox_base_dir = self.cwd / ".worktree" / "sandboxes"
        self._config: WorktreeConfig | None = None

    def _ensure_sandbox_dir(self) -> None:
        """Create the parent sandbox storage directory if missing."""
        self.sandbox_base_dir.mkdir(parents=True, exist_ok=True)

    def _run_git_cmd(self, args: list[str], cwd: Path | None = None) -> str:
        """Execute a git command and return stripped stdout.

        Args:
            args: Git arguments after ``git``.
            cwd: Working directory for the command.

        Returns:
            Stripped stdout text.

        Raises:
            RuntimeError: When git exits non-zero.
        """
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
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Git execution failed ('git {' '.join(args)}'): git not found"
            ) from exc
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise RuntimeError(
                f"Git execution failed ('git {' '.join(args)}'): {err_msg}"
            ) from exc

    def get_active_sandboxes(self) -> list[Path]:
        """List immediate child directories under the sandbox base path.

        Returns:
            Sandbox directory paths, or an empty list when the base is missing.
        """
        if not self.sandbox_base_dir.exists():
            return []
        return [p for p in self.sandbox_base_dir.iterdir() if p.is_dir()]

    def _discard_partial_sandbox(self, sandbox_path: Path, temp_branch: str) -> None:
        """Best-effort remove of a partial worktree/branch after failed create."""
        if sandbox_path.exists():
            try:
                self._run_git_cmd(["worktree", "remove", "--force", str(sandbox_path)])
            except RuntimeError:
                shutil.rmtree(sandbox_path, ignore_errors=True)
        try:
            self._run_git_cmd(["branch", "-D", temp_branch])
        except RuntimeError:
            pass
        try:
            self._run_git_cmd(["worktree", "prune"])
        except RuntimeError:
            pass

    def create_sandbox_result(
        self,
        session_id: str | None = None,
        *,
        include_wip: bool = False,
    ) -> SandboxCreateResult:
        """Create a sandbox without raising for classified failures.

        Args:
            session_id: Optional fixed session id; otherwise ``sbx_`` + 8 hex.
            include_wip: When True, overlay uncommitted working-tree changes
                from the primary checkout into the new sandbox.

        Returns:
            Structured create result with session on success.
        """
        load = load_config_result(cwd=self.cwd)
        if load.status == ConfigLoadStatus.NOT_FOUND:
            return SandboxCreateResult(
                status=SandboxCreateStatus.NOT_INITIALIZED,
                errors=[_not_initialized_error(load.config_path)],
            )
        if not load.ok or load.config is None:
            detail = load.errors[0] if load.errors else str(load.status)
            return SandboxCreateResult(
                status=SandboxCreateStatus.UNREADABLE_CONFIG,
                errors=[_unreadable_config_error(detail)],
            )

        config = load.config
        self._config = config

        self._ensure_sandbox_dir()
        active_sandboxes = self.get_active_sandboxes()
        max_allowed = config.sandbox.max_active_sandboxes
        if len(active_sandboxes) >= max_allowed:
            return SandboxCreateResult(
                status=SandboxCreateStatus.CAPACITY_EXCEEDED,
                errors=[_capacity_error(len(active_sandboxes), max_allowed)],
            )

        sid = session_id or f"sbx_{uuid.uuid4().hex[:8]}"
        sandbox_path = (self.sandbox_base_dir / sid).resolve()
        temp_branch = f"worktree/sandbox-{sid}"

        source_branch = get_current_git_branch(self.cwd)
        base_ref = (
            source_branch
            if source_branch not in ("unknown", "HEAD (detached)")
            else config.sandbox.base_ref
        )

        try:
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
        except RuntimeError as exc:
            self._discard_partial_sandbox(sandbox_path, temp_branch)
            return SandboxCreateResult(
                status=SandboxCreateStatus.GIT_FAILED,
                errors=[_git_failed_error(str(exc))],
            )

        wip_paths: list[str] = []
        if include_wip:
            try:
                wip_paths = apply_wip_to_sandbox(
                    source_root=self.cwd,
                    sandbox_path=sandbox_path,
                )
            except RuntimeError as exc:
                self._discard_partial_sandbox(sandbox_path, temp_branch)
                return SandboxCreateResult(
                    status=SandboxCreateStatus.WIP_FAILED,
                    errors=[_wip_failed_error(str(exc))],
                )

        session = SandboxSession(
            session_id=sid,
            target_branch=temp_branch,
            sandbox_path=sandbox_path,
            created_at=datetime.now(UTC).isoformat(),
            wip_applied=bool(include_wip),
            wip_paths=wip_paths,
        )
        return SandboxCreateResult(status=SandboxCreateStatus.OK, session=session)

    def create_sandbox(
        self,
        session_id: str | None = None,
        *,
        include_wip: bool = False,
    ) -> SandboxSession:
        """Create a sandbox or raise with the classified error message.

        Args:
            session_id: Optional fixed session id.
            include_wip: When True, overlay uncommitted working-tree changes.

        Returns:
            Created session metadata.

        Raises:
            RuntimeError: When creation fails for any classified reason.
        """
        result = self.create_sandbox_result(
            session_id=session_id,
            include_wip=include_wip,
        )
        if not result.ok or result.session is None:
            message = (
                result.errors[0]
                if result.errors
                else f"Sandbox create failed: {result.status}"
            )
            raise RuntimeError(message)
        return result.session

    def cleanup_sandbox(self, session: SandboxSession, *, force: bool = True) -> None:
        """Remove worktree, delete throwaway branch, and prune (idempotent).

        Args:
            session: Session returned from create.
            force: Pass ``--force`` to ``git worktree remove`` when True.
        """
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

        try:
            self.prune()
        except RuntimeError:
            pass

    def prune(self) -> None:
        """Prune stale Git worktree registrations."""
        self._run_git_cmd(["worktree", "prune"])


@contextmanager
def sandbox_scope(
    cwd: Path | None = None,
    session_id: str | None = None,
    *,
    auto_clean: bool | None = None,
    keep_on_failure: bool | None = None,
    include_wip: bool = False,
) -> Generator[SandboxSession]:
    """Create a sandbox and optionally clean it up on exit.

    Cleanup flags come from explicit kwargs when provided; otherwise from
    loaded config ``sandbox.auto_clean`` / ``sandbox.keep_on_failure``.

    Args:
        cwd: Repository root.
        session_id: Optional fixed session id.
        auto_clean: Override config auto_clean when not None.
        keep_on_failure: Override config keep_on_failure when not None.
        include_wip: Overlay uncommitted working-tree changes when True.

    Yields:
        The created ``SandboxSession``.

    Raises:
        RuntimeError: When sandbox creation fails.
    """
    manager = GitSandboxManager(cwd=cwd)
    result = manager.create_sandbox_result(
        session_id=session_id,
        include_wip=include_wip,
    )
    if not result.ok or result.session is None:
        message = (
            result.errors[0]
            if result.errors
            else f"Sandbox create failed: {result.status}"
        )
        raise RuntimeError(message)

    session = result.session
    cfg = manager._config
    resolved_auto = (
        auto_clean
        if auto_clean is not None
        else (cfg.sandbox.auto_clean if cfg is not None else True)
    )
    resolved_keep = (
        keep_on_failure
        if keep_on_failure is not None
        else (cfg.sandbox.keep_on_failure if cfg is not None else True)
    )

    try:
        yield session
    finally:
        if should_cleanup_sandbox(
            auto_clean=resolved_auto,
            keep_on_failure=resolved_keep,
            command_passed=session.command_passed,
        ):
            manager.cleanup_sandbox(session)
