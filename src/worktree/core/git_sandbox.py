"""Orchestrate native Git worktree sandboxes for isolated command execution."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from worktree.common.constants import GIT_SUBPROCESS_TIMEOUT_SECONDS
from worktree.common.git import get_current_git_branch
from worktree.core.config.loader import ConfigLoadStatus, load_config_result
from worktree.core.config.models import WorktreeConfig
from worktree.core.db import SandboxesRepository, SandboxRecord, SandboxStatus
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxApplyStrategy,
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxDiffResult,
    SandboxDiffStatus,
    SandboxSession,
)

__all__ = [
    "GitPlumbingTimeoutError",
    "GitSandboxManager",
    "SandboxApplyResult",
    "SandboxApplyStatus",
    "SandboxApplyStrategy",
    "SandboxCreateResult",
    "SandboxCreateStatus",
    "SandboxDiffResult",
    "SandboxDiffStatus",
    "SandboxSession",
    "apply_wip_to_sandbox",
]


class GitPlumbingTimeoutError(RuntimeError):
    """Raised when an internal git plumbing subprocess exceeds its timeout."""


def _clean_opt_str(val: str | None) -> str | None:
    if val is None:
        return None
    s = val.strip()
    return s if s else None


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
            timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitPlumbingTimeoutError(
            f"Git timed out after {GIT_SUBPROCESS_TIMEOUT_SECONDS}s ('git status --porcelain -u') (GIT_TIMEOUT)"
        ) from exc
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


def _remove_dst(dst: Path) -> None:
    """Remove *dst* regardless of whether it is a file, symlink, or directory."""
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()


def _copy_wip_file(source_root: Path, dest_root: Path, rel: str) -> None:
    """Mirror a single working-tree path from *source_root* into *dest_root*.

    Behaviour by case:

    - **Source deleted**: remove the corresponding destination path (file,
      symlink, or directory tree) so the sandbox stays in sync.
    - **Source is a plain directory**: skip — directory entries are created
      implicitly when their children are copied.
    - **Source is a symlink**: recreate the symlink at the destination,
      replacing whatever was there before.
    - **Source is a regular file**: copy the file (preserving metadata via
      :func:`shutil.copy2`), creating any missing parent directories.

    Args:
        source_root: Absolute path to the primary repository checkout.
        dest_root: Absolute path to the sandbox worktree.
        rel: Repo-relative path of the entry to mirror.
    """
    src = source_root / rel
    dst = dest_root / rel
    if not src.exists():
        _remove_dst(dst)
        return
    if src.is_dir() and not src.is_symlink():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        _remove_dst(dst)
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

    def __init__(
        self,
        path: Path,
        db: SandboxesRepository | None = None,
    ) -> None:
        """Bind to an absolute repository root.

        Args:
            path: Repository root.
            db: Optional SandboxesRepository instance.
        """
        self.path = path.expanduser().resolve()
        self.cwd = self.path
        self.sandbox_base_dir = self.path / ".worktree" / "sandboxes"
        self.db = db if db is not None else SandboxesRepository(self.path)
        self._config: WorktreeConfig | None = None

    @property
    def config(self) -> WorktreeConfig | None:
        """Return the config last loaded by a successful create attempt.

        Populated when ``create_sandbox_result`` loads config successfully.
        ``None`` before the first successful load or when create failed before
        assigning config.
        """
        return self._config

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
                timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
            )
            return result.stdout.strip()
        except FileNotFoundError as exc:
            raise RuntimeError(f"Git execution failed ('git {' '.join(args)}'): git not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitPlumbingTimeoutError(
                f"Git timed out after {GIT_SUBPROCESS_TIMEOUT_SECONDS}s ('git {' '.join(args)}') (GIT_TIMEOUT)"
            ) from exc
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise RuntimeError(f"Git execution failed ('git {' '.join(args)}'): {err_msg}") from exc

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

    # ------------------------------------------------------------------
    # create_sandbox_result helpers
    # ------------------------------------------------------------------

    def _load_and_validate_config(
        self,
    ) -> tuple[SandboxCreateResult, None] | tuple[None, WorktreeConfig]:
        """Load and validate worktree config.

        Returns:
            ``(error_result, None)`` when config is missing or unreadable,
            ``(None, config)`` on success.
        """
        load = load_config_result(path=self.path)
        if load.status == ConfigLoadStatus.NOT_FOUND:
            return (
                SandboxCreateResult(
                    status=SandboxCreateStatus.NOT_INITIALIZED,
                    errors=[
                        f"Worktree is not initialized; config missing at "
                        f"'{load.config_path}' (SANDBOX_NOT_INITIALIZED).\n"
                        "Fix:\n"
                        "- run `wt init` to create `.worktree/config.json`"
                    ],
                ),
                None,
            )
        if not load.ok or load.config is None:
            detail = load.errors[0] if load.errors else str(load.status)
            return (
                SandboxCreateResult(
                    status=SandboxCreateStatus.UNREADABLE_CONFIG,
                    errors=[
                        f"Unable to load Worktree config for sandbox create "
                        f"(SANDBOX_CONFIG_UNREADABLE): {detail}\n"
                        "Fix:\n"
                        "- repair `.worktree/config.json` or run `wt init --repair`"
                    ],
                ),
                None,
            )
        self._config = load.config
        return None, load.config

    def _check_capacity(self, config: WorktreeConfig) -> SandboxCreateResult | None:
        """Return an error result when the active-sandbox cap has been reached."""
        active = self.get_active_sandboxes()
        max_allowed = config.sandbox.max_active_sandboxes
        if len(active) >= max_allowed:
            return SandboxCreateResult(
                status=SandboxCreateStatus.CAPACITY_EXCEEDED,
                errors=[
                    f"Maximum active sandboxes reached "
                    f"({len(active)}/{max_allowed}).\n"
                    "Fix:\n"
                    "- run `wt prune` to remove stale sandboxes, or\n"
                    "- raise sandbox.max_active_sandboxes in .worktree/config.json"
                ],
            )
        return None

    def _resolve_base_ref(self, override_base_ref: str | None, config: WorktreeConfig) -> str:
        """Return the git ref to branch the sandbox from.

        Uses *override_base_ref* when provided; otherwise falls back to the
        current branch or the configured ``sandbox.base_ref``.
        """
        if override_base_ref is not None:
            return override_base_ref
        source_branch = get_current_git_branch(self.cwd)
        if source_branch not in ("unknown", "HEAD (detached)"):
            return source_branch
        return config.sandbox.base_ref

    def _run_git_worktree_add(
        self,
        sandbox_path: Path,
        temp_branch: str,
        resolved_base_ref: str,
    ) -> SandboxCreateResult | None:
        """Run ``git worktree add`` and return an error result on failure."""
        try:
            self._run_git_cmd(["worktree", "add", "-b", temp_branch, str(sandbox_path), resolved_base_ref])
            return None
        except GitPlumbingTimeoutError as exc:
            self._discard_partial_sandbox(sandbox_path, temp_branch)
            return SandboxCreateResult(
                status=SandboxCreateStatus.GIT_TIMEOUT,
                errors=[
                    f"Git worktree operation timed out "
                    f"(SANDBOX_GIT_TIMEOUT): {exc}\n"
                    "Fix:\n"
                    "- check for git lock files, credential prompts, or a "
                    "stuck git process, then retry"
                ],
            )
        except RuntimeError as exc:
            self._discard_partial_sandbox(sandbox_path, temp_branch)
            return SandboxCreateResult(
                status=SandboxCreateStatus.GIT_FAILED,
                errors=[
                    f"Git worktree operation failed (SANDBOX_GIT_FAILED): {exc}\n"
                    "Fix:\n"
                    "- ensure this directory is a Git repository with a valid "
                    "base ref"
                ],
            )

    def _get_base_commit(
        self,
        sandbox_path: Path,
        temp_branch: str,
    ) -> tuple[str, None] | tuple[None, SandboxCreateResult]:
        """Resolve HEAD of the new worktree.

        Returns:
            ``(commit_sha, None)`` on success,
            ``(None, error_result)`` on git failure.
        """
        try:
            commit = self._run_git_cmd(["rev-parse", "HEAD"], cwd=sandbox_path)
            return commit, None
        except GitPlumbingTimeoutError as exc:
            self._discard_partial_sandbox(sandbox_path, temp_branch)
            return None, SandboxCreateResult(
                status=SandboxCreateStatus.GIT_TIMEOUT,
                errors=[
                    f"Git worktree operation timed out "
                    f"(SANDBOX_GIT_TIMEOUT): {exc}\n"
                    "Fix:\n"
                    "- check for git lock files, credential prompts, or a "
                    "stuck git process, then retry"
                ],
            )
        except RuntimeError as exc:
            self._discard_partial_sandbox(sandbox_path, temp_branch)
            return None, SandboxCreateResult(
                status=SandboxCreateStatus.GIT_FAILED,
                errors=[
                    f"Git worktree operation failed (SANDBOX_GIT_FAILED): {exc}\n"
                    "Fix:\n"
                    "- ensure this directory is a Git repository with a valid "
                    "base ref"
                ],
            )

    def _apply_wip_overlay(
        self,
        sandbox_path: Path,
        temp_branch: str,
    ) -> tuple[list[str], None] | tuple[None, SandboxCreateResult]:
        """Overlay uncommitted working-tree changes into *sandbox_path*.

        Returns:
            ``(wip_paths, None)`` on success,
            ``(None, error_result)`` on failure.
        """
        try:
            paths = apply_wip_to_sandbox(source_root=self.cwd, sandbox_path=sandbox_path)
            return paths, None
        except GitPlumbingTimeoutError as exc:
            self._discard_partial_sandbox(sandbox_path, temp_branch)
            return None, SandboxCreateResult(
                status=SandboxCreateStatus.GIT_TIMEOUT,
                errors=[
                    f"Git timed out while overlaying uncommitted WIP "
                    f"(SANDBOX_GIT_TIMEOUT): {exc}\n"
                    "Fix:\n"
                    "- check for git lock files or a stuck git process, "
                    "then retry, or\n"
                    "- omit --wip and commit changes first"
                ],
            )
        except RuntimeError as exc:
            self._discard_partial_sandbox(sandbox_path, temp_branch)
            return None, SandboxCreateResult(
                status=SandboxCreateStatus.WIP_FAILED,
                errors=[
                    f"Failed to overlay uncommitted WIP into sandbox "
                    f"(SANDBOX_WIP_FAILED): {exc}\n"
                    "Fix:\n"
                    "- resolve local conflicts / binary issues and retry, or\n"
                    "- omit --wip and commit changes first"
                ],
            )

    def _persist_sandbox_session(self, session: SandboxSession) -> list[str]:
        """Insert *session* into the local DB; return any warning messages."""
        try:
            self.db.create(
                id=session.session_id,
                name=session.name,
                branch_name=session.target_branch,
                base_commit=session.base_commit,
                sandbox_path=session.sandbox_path,
            )
            return []
        except Exception as exc:
            return [f"Failed to persist sandbox metadata to the local database: {exc}"]

    def _collect_wip_paths(
        self,
        include_wip: bool,
        sandbox_path: Path,
        temp_branch: str,
    ) -> tuple[list[str], None] | tuple[None, SandboxCreateResult]:
        """Return WIP paths to overlay, or an error result.

        When *include_wip* is ``False`` returns an empty list immediately.
        Otherwise delegates to :meth:`_apply_wip_overlay`.

        Returns:
            ``(paths, None)`` on success, ``(None, error_result)`` on failure.
        """
        if not include_wip:
            return [], None
        return self._apply_wip_overlay(sandbox_path, temp_branch)

    def _build_session(
        self,
        *,
        sid: str,
        temp_branch: str,
        sandbox_path: Path,
        base_commit: str,
        resolved_name: str | None,
        include_wip: bool,
        wip_paths: list[str],
    ) -> SandboxSession:
        """Construct and return a :class:`SandboxSession` from resolved fields."""
        return SandboxSession(
            session_id=sid,
            target_branch=temp_branch,
            sandbox_path=sandbox_path,
            base_commit=base_commit,
            name=resolved_name,
            created_at=datetime.now(UTC).isoformat(),
            wip_applied=bool(include_wip),
            wip_paths=wip_paths,
        )

    def _prepare_sandbox_session(
        self,
        *,
        sid: str,
        sandbox_path: Path,
        temp_branch: str,
        resolved_base_ref: str,
        resolved_name: str | None,
        include_wip: bool,
    ) -> tuple[SandboxCreateResult | None, SandboxSession | None]:
        add_err = self._run_git_worktree_add(sandbox_path, temp_branch, resolved_base_ref)
        if add_err is not None:
            return add_err, None

        base_commit, commit_err = self._get_base_commit(sandbox_path, temp_branch)
        if commit_err is not None or base_commit is None:
            return commit_err or SandboxCreateResult(
                status=SandboxCreateStatus.GIT_FAILED,
                errors=["Failed to determine base commit"],
            ), None

        wip_paths, wip_err = self._collect_wip_paths(include_wip, sandbox_path, temp_branch)
        if wip_err is not None or wip_paths is None:
            return wip_err or SandboxCreateResult(
                status=SandboxCreateStatus.GIT_FAILED,
                errors=["Failed to collect WIP paths"],
            ), None

        session = self._build_session(
            sid=sid,
            temp_branch=temp_branch,
            sandbox_path=sandbox_path,
            base_commit=base_commit,
            resolved_name=resolved_name,
            include_wip=include_wip,
            wip_paths=wip_paths,
        )
        return None, session

    def create_sandbox_result(
        self,
        session_id: str | None = None,
        *,
        include_wip: bool = False,
        name: str | None = None,
        base_ref: str | None = None,
    ) -> SandboxCreateResult:
        """Create a sandbox without raising for classified failures.

        Orchestrates config loading, capacity checks, worktree creation, and
        optional WIP overlay. Each phase is delegated to a private helper so
        that errors are returned as structured :class:`SandboxCreateResult`
        values rather than exceptions.

        Args:
            session_id: Optional fixed session id; otherwise ``sbx_`` + 8 hex.
            include_wip: When True, overlay uncommitted working-tree changes.
            name: Optional human-readable sandbox name. Whitespace-only values
                are stored as ``None``.
            base_ref: Optional git ref for ``git worktree add``.

        Returns:
            Structured create result with session on success.
        """
        resolved_name = _clean_opt_str(name)
        override_base_ref = _clean_opt_str(base_ref)

        config_err, config = self._load_and_validate_config()
        if config_err is not None or config is None:
            return config_err or SandboxCreateResult(
                status=SandboxCreateStatus.NOT_INITIALIZED,
                errors=["Configuration not loaded"],
            )

        self._ensure_sandbox_dir()
        capacity_err = self._check_capacity(config)
        if capacity_err is not None:
            return capacity_err

        sid = session_id or f"sbx_{uuid.uuid4().hex[:8]}"
        sandbox_path = (self.sandbox_base_dir / sid).resolve()
        temp_branch = f"worktree/sandbox-{sid}"
        resolved_base_ref = self._resolve_base_ref(override_base_ref, config)

        err, session = self._prepare_sandbox_session(
            sid=sid,
            sandbox_path=sandbox_path,
            temp_branch=temp_branch,
            resolved_base_ref=resolved_base_ref,
            resolved_name=resolved_name,
            include_wip=include_wip,
        )
        if err is not None or session is None:
            return err or SandboxCreateResult(
                status=SandboxCreateStatus.GIT_FAILED,
                errors=["Failed to prepare sandbox session"],
            )

        warnings = self._persist_sandbox_session(session)
        return SandboxCreateResult(
            status=SandboxCreateStatus.OK,
            session=session,
            warnings=warnings,
        )

    def create_sandbox(
        self,
        session_id: str | None = None,
        *,
        include_wip: bool = False,
        name: str | None = None,
        base_ref: str | None = None,
    ) -> SandboxSession:
        """Create a sandbox or raise with the classified error message.

        Args:
            session_id: Optional fixed session id.
            include_wip: When True, overlay uncommitted working-tree changes.
            name: Optional human-readable sandbox name.
            base_ref: Optional git ref override for worktree creation.

        Returns:
            Created session metadata.

        Raises:
            RuntimeError: When creation fails for any classified reason.
        """
        result = self.create_sandbox_result(
            session_id=session_id,
            include_wip=include_wip,
            name=name,
            base_ref=base_ref,
        )
        if not result.ok or result.session is None:
            message = result.errors[0] if result.errors else f"Sandbox create failed: {result.status}"
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
            self.db.update_status(
                session.session_id,
                SandboxStatus.CLEANED,
            )
        except Exception:
            # Intentional best-effort local-DB bookkeeping during cleanup:
            # worktree removal and branch deletion proceed independently.
            pass

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

    # ------------------------------------------------------------------
    # apply_sandbox_result helpers
    # ------------------------------------------------------------------

    def _validate_sandbox_for_apply(
        self,
        sandbox_id: str,
    ) -> tuple[SandboxRecord | None, SandboxApplyResult | None]:
        """Validate that sandbox exists in DB, is on disk, and is not already merged."""
        record = self.db.get(sandbox_id)
        if record is None:
            return None, SandboxApplyResult(
                status=SandboxApplyStatus.NOT_FOUND,
                sandbox_id=sandbox_id,
                errors=[f"Sandbox '{sandbox_id}' not found.\nFix:\n- run `wt sandbox list` to see known sandboxes"],
            )

        if not Path(record.sandbox_path).is_dir():
            self.db.reconcile_stale_active(sandbox_id)
            return None, SandboxApplyResult(
                status=SandboxApplyStatus.NOT_FOUND,
                sandbox_id=sandbox_id,
                errors=[f"Sandbox '{sandbox_id}' directory is missing on disk; reconciled status to 'cleaned'."],
            )

        if record.status == SandboxStatus.MERGED:
            return None, SandboxApplyResult(
                status=SandboxApplyStatus.ALREADY_MERGED,
                sandbox_id=sandbox_id,
                warnings=[f"Sandbox '{sandbox_id}' is already merged."],
            )

        return record, None

    def _check_main_repo_clean(
        self,
        allow_dirty: bool,
        sandbox_id: str,
    ) -> SandboxApplyResult | None:
        """Check if main repository has uncommitted changes."""
        if allow_dirty:
            return None

        dirty_paths = _list_wip_paths(self.path)
        if not dirty_paths:
            return None

        return SandboxApplyResult(
            status=SandboxApplyStatus.MAIN_REPO_DIRTY,
            sandbox_id=sandbox_id,
            errors=[
                f"Cannot apply sandbox {sandbox_id}: main repository has uncommitted changes.\n"
                "Fix:\n"
                "- commit or stash local changes in the main workspace, or\n"
                "- pass --allow-dirty to overlay changes anyway"
            ],
        )

    def _collect_sandbox_changes(
        self,
        record: SandboxRecord,
    ) -> tuple[str, list[str], SandboxApplyResult | None]:
        """Generate unified diff and list of touched files."""
        try:
            diff_text, touched_files, _ = _collect_sandbox_delta(Path(record.sandbox_path), record.base_commit)
        except Exception as exc:
            return (
                "",
                [],
                SandboxApplyResult(
                    status=SandboxApplyStatus.GIT_FAILED,
                    sandbox_id=record.id,
                    errors=[f"Failed to generate diff from sandbox: {exc}"],
                ),
            )

        if not touched_files or not diff_text.strip():
            return (
                "",
                [],
                SandboxApplyResult(
                    status=SandboxApplyStatus.EMPTY_DIFF,
                    sandbox_id=record.id,
                    warnings=[f"Sandbox '{record.id}' has no changes to apply."],
                ),
            )

        return diff_text, touched_files, None

    def _verify_patch_cleanliness(
        self,
        diff_text: str,
        sandbox_id: str,
    ) -> tuple[list[str], SandboxApplyResult | None]:
        """Perform dry-run conflict check with git apply --check."""
        try:
            proc = subprocess.run(
                ["git", "apply", "--check", "--binary", "-"],
                cwd=str(self.path),
                input=diff_text + "\n",
                capture_output=True,
                text=True,
                timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            return [], SandboxApplyResult(
                status=SandboxApplyStatus.GIT_FAILED,
                sandbox_id=sandbox_id,
                errors=[f"Git timeout during conflict check: {exc}"],
            )
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            return [], SandboxApplyResult(
                status=SandboxApplyStatus.GIT_FAILED,
                sandbox_id=sandbox_id,
                errors=[f"Git failure during conflict check: {exc}"],
            )

        if proc.returncode != 0:
            conflicts = _extract_conflicts(proc.stderr)
            self.db.update_status(sandbox_id, SandboxStatus.CONFLICT)
            conflict_bullets = "\n".join(f"  • {f}" for f in conflicts) if conflicts else f"  {proc.stderr.strip()}"
            return conflicts, SandboxApplyResult(
                status=SandboxApplyStatus.CONFLICT,
                sandbox_id=sandbox_id,
                conflicting_files=conflicts,
                errors=[
                    f"Cannot apply sandbox {sandbox_id}: conflicts detected.\n"
                    f"Conflicting files:\n{conflict_bullets}\n"
                    "Fix:\n"
                    f"- inspect sandbox differences with `wt sandbox diff {sandbox_id}`\n"
                    "- resolve conflicts in the main workspace or sandbox worktree"
                ],
            )

        return [], None

    def _apply_patch_strategy(
        self,
        diff_text: str,
        strategy: SandboxApplyStrategy,
        message: str | None,
        sandbox_id: str,
    ) -> tuple[str | None, SandboxApplyResult | None]:
        """Apply patch to working directory and optionally commit if squash."""
        try:
            apply_proc = subprocess.run(
                ["git", "apply", "--binary", "-"],
                cwd=str(self.path),
                input=diff_text + "\n",
                capture_output=True,
                text=True,
                timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            return None, SandboxApplyResult(
                status=SandboxApplyStatus.GIT_FAILED,
                sandbox_id=sandbox_id,
                errors=[f"Git apply failed: {exc}"],
            )

        if apply_proc.returncode != 0:
            err_detail = apply_proc.stderr.strip() or apply_proc.stdout.strip()
            return None, SandboxApplyResult(
                status=SandboxApplyStatus.GIT_FAILED,
                sandbox_id=sandbox_id,
                errors=[f"Git apply failed: {err_detail}"],
            )

        if strategy != SandboxApplyStrategy.SQUASH:
            return None, None

        commit_msg = message or f"wt: apply changes from sandbox {sandbox_id}"
        try:
            self._run_git_cmd(["add", "-A"], cwd=self.path)
            self._run_git_cmd(["commit", "-m", commit_msg], cwd=self.path)
            commit_sha = self._run_git_cmd(["rev-parse", "HEAD"], cwd=self.path)
            return commit_sha, None
        except Exception as exc:
            return None, SandboxApplyResult(
                status=SandboxApplyStatus.GIT_FAILED,
                sandbox_id=sandbox_id,
                errors=[f"Git squash commit failed: {exc}"],
            )

    def _cleanup_after_apply(self, record: SandboxRecord, delete: bool) -> bool:
        """Clean up sandbox worktree and branch if delete requested."""
        if not delete:
            return False

        session = SandboxSession(
            session_id=record.id,
            target_branch=record.branch_name,
            sandbox_path=record.sandbox_path,
            base_commit=record.base_commit,
            name=record.name,
            created_at=record.created_at,
        )
        self.cleanup_sandbox(session)
        return True

    def apply_sandbox_result(
        self,
        sandbox_id: str,
        *,
        strategy: SandboxApplyStrategy = SandboxApplyStrategy.PATCH,
        allow_dirty: bool = False,
        dry_run: bool = False,
        delete: bool = False,
        message: str | None = None,
    ) -> SandboxApplyResult:
        """Apply sandbox changes back to main workspace without raising."""
        record, val_err = self._validate_sandbox_for_apply(sandbox_id)
        if val_err is not None or record is None:
            return val_err or SandboxApplyResult(
                status=SandboxApplyStatus.NOT_FOUND,
                sandbox_id=sandbox_id,
                errors=["Validation failed"],
            )

        dirty_err = self._check_main_repo_clean(allow_dirty, sandbox_id)
        if dirty_err is not None:
            return dirty_err

        diff_text, touched_files, coll_err = self._collect_sandbox_changes(record)
        if coll_err is not None:
            return coll_err

        _, conflict_err = self._verify_patch_cleanliness(diff_text, sandbox_id)
        if conflict_err is not None:
            return conflict_err

        if dry_run:
            return SandboxApplyResult(
                status=SandboxApplyStatus.OK,
                sandbox_id=sandbox_id,
                strategy=strategy,
                touched_files=touched_files,
                warnings=["Dry run validation succeeded. No files were modified."],
            )

        commit_sha, apply_err = self._apply_patch_strategy(diff_text, strategy, message, sandbox_id)
        if apply_err is not None:
            return apply_err

        self.db.update_status(sandbox_id, SandboxStatus.MERGED)
        cleaned_up = self._cleanup_after_apply(record, delete)

        return SandboxApplyResult(
            status=SandboxApplyStatus.OK,
            sandbox_id=sandbox_id,
            strategy=strategy,
            touched_files=touched_files,
            commit_sha=commit_sha,
            cleaned_up=cleaned_up,
        )

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
        """Apply sandbox changes or raise with classified error message."""
        result = self.apply_sandbox_result(
            sandbox_id,
            strategy=strategy,
            allow_dirty=allow_dirty,
            dry_run=dry_run,
            delete=delete,
            message=message,
        )
        if not result.ok:
            msg = result.errors[0] if result.errors else f"Sandbox apply failed: {result.status}"
            raise RuntimeError(msg)
        return result

    # ------------------------------------------------------------------
    # diff_sandbox_result helpers
    # ------------------------------------------------------------------

    def _validate_sandbox_for_diff(
        self,
        sandbox_id: str,
    ) -> tuple[SandboxRecord | None, SandboxDiffResult | None]:
        """Validate sandbox record for diff inspection."""
        record = self.db.get(sandbox_id)
        if record is None:
            return None, SandboxDiffResult(
                status=SandboxDiffStatus.NOT_FOUND,
                sandbox_id=sandbox_id,
                errors=[f"Sandbox '{sandbox_id}' not found."],
            )
        if not Path(record.sandbox_path).is_dir():
            self.db.reconcile_stale_active(sandbox_id)
            return None, SandboxDiffResult(
                status=SandboxDiffStatus.NOT_FOUND,
                sandbox_id=sandbox_id,
                errors=[f"Sandbox '{sandbox_id}' directory is missing on disk."],
            )
        return record, None

    def diff_sandbox_result(
        self,
        sandbox_id: str,
        *,
        stat: bool = False,
    ) -> SandboxDiffResult:
        """Inspect unified diff or file summary statistics for a sandbox."""
        record, val_err = self._validate_sandbox_for_diff(sandbox_id)
        if val_err is not None or record is None:
            return val_err or SandboxDiffResult(
                status=SandboxDiffStatus.NOT_FOUND,
                sandbox_id=sandbox_id,
                errors=["Validation failed"],
            )

        try:
            diff_text, touched_files, stat_text = _collect_sandbox_delta(Path(record.sandbox_path), record.base_commit)
        except Exception as exc:
            return SandboxDiffResult(
                status=SandboxDiffStatus.GIT_FAILED,
                sandbox_id=sandbox_id,
                errors=[f"Failed to generate diff for sandbox '{sandbox_id}': {exc}"],
            )

        if not touched_files or not diff_text.strip():
            return SandboxDiffResult(
                status=SandboxDiffStatus.EMPTY_DIFF,
                sandbox_id=sandbox_id,
                warnings=[f"Sandbox '{sandbox_id}' has no changes compared to base commit."],
            )

        return SandboxDiffResult(
            status=SandboxDiffStatus.OK,
            sandbox_id=sandbox_id,
            diff_text=diff_text,
            stat_text=stat_text,
            files_changed=touched_files,
        )

    def diff_sandbox(
        self,
        sandbox_id: str,
        *,
        stat: bool = False,
    ) -> SandboxDiffResult:
        """Inspect sandbox diff or raise with classified error message."""
        result = self.diff_sandbox_result(sandbox_id, stat=stat)
        if not result.ok:
            msg = result.errors[0] if result.errors else f"Sandbox diff failed: {result.status}"
            raise RuntimeError(msg)
        return result


_CONFLICT_PATTERNS = (
    re.compile(r"^error:\s+patch failed:\s+([^:]+)"),
    re.compile(r"^error:\s+([^:]+):\s+patch does not apply"),
    re.compile(r"cannot apply binary patch to '([^']+)'"),
    re.compile(r"^error:\s+([^:]+):\s+(?:already exists in working directory|does not exist in index)"),
)


def _match_conflict_line(line: str) -> str | None:
    """Return conflicting file path from a single line of git stderr, or None."""
    trimmed = line.strip()
    for pattern in _CONFLICT_PATTERNS:
        match = pattern.search(trimmed)
        if match:
            return match.group(1).strip()
    return None


def _extract_conflicts(stderr: str) -> list[str]:
    """Extract conflicting file paths from git apply stderr output."""
    conflicts: set[str] = set()
    for line in stderr.splitlines():
        path = _match_conflict_line(line)
        if path:
            conflicts.add(path)
    return sorted(conflicts)


def _collect_sandbox_delta(sandbox_path: Path, base_commit: str) -> tuple[str, list[str], str]:
    """Collect untracked changes into index with intent-to-add and compute unified diff and name list.

    Returns:
        Tuple of (unified_diff_text, list_of_touched_files, stat_text).
    """
    try:
        subprocess.run(
            ["git", "add", "-N", "."],
            cwd=str(sandbox_path),
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    diff_proc = subprocess.run(
        ["git", "diff", "--binary", base_commit],
        cwd=str(sandbox_path),
        capture_output=True,
        text=True,
        check=True,
        timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
    )
    name_proc = subprocess.run(
        ["git", "diff", "--name-only", base_commit],
        cwd=str(sandbox_path),
        capture_output=True,
        text=True,
        check=True,
        timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
    )
    stat_proc = subprocess.run(
        ["git", "diff", "--stat", base_commit],
        cwd=str(sandbox_path),
        capture_output=True,
        text=True,
        check=True,
        timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
    )
    diff_text = diff_proc.stdout
    touched_files = [line.strip() for line in name_proc.stdout.splitlines() if line.strip()]
    stat_text = stat_proc.stdout
    return diff_text, touched_files, stat_text
