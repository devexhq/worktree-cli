"""Concurrency integration tests for GitSandboxManager."""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import Any

from tests.helpers import GitFileSystem
from worktree.core.db import SandboxesRepository, SandboxStatus
from worktree.core.sandbox import GitSandboxManager


def _worker_create_sandbox(
    repo_path: Path,
    name: str,
    result_queue: multiprocessing.Queue,  # type: ignore[reportMissingTypeArgument]
) -> None:
    """Worker process that instantiates a repository/manager and creates a sandbox."""
    try:
        db = SandboxesRepository(repo_path)
        manager = GitSandboxManager(path=repo_path, db=db)
        result = manager.create_sandbox(name=name)
        if result.ok and result.session is not None:
            result_queue.put(
                {
                    "ok": True,
                    "session_id": result.session.session_id,
                    "branch_name": result.session.target_branch,
                    "path": str(result.session.sandbox_path),
                }
            )
        else:
            result_queue.put({"ok": False, "errors": result.errors})
    except Exception as exc:
        result_queue.put({"ok": False, "errors": [str(exc)]})


def _worker_cleanup_sandbox(
    repo_path: Path,
    session_id: str,
    result_queue: multiprocessing.Queue,  # type: ignore[reportMissingTypeArgument]
) -> None:
    """Worker process that cleans up a sandbox by session id."""
    try:
        db = SandboxesRepository(repo_path)
        record = db.get(session_id)
        if record is None:
            result_queue.put({"ok": False, "errors": [f"Record {session_id} not found"]})
            return

        manager = GitSandboxManager(path=repo_path, db=db)
        warnings = manager.cleanup_sandbox(record)
        result_queue.put({"ok": True, "warnings": warnings})
    except Exception as exc:
        result_queue.put({"ok": False, "errors": [str(exc)]})


class TestConcurrentSandboxOperations:
    """Integration tests verifying cross-process concurrency safety on sandboxes."""

    def test_concurrent_sandbox_creation_and_cleanup(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        git_fs.create_config_file(sandbox={"max_active_sandboxes": 10})

        ctx = multiprocessing.get_context("spawn")
        result_queue = ctx.Queue()

        concurrency_count = 3
        processes: list[multiprocessing.Process] = []

        # 1. Launch 3 concurrent sandbox creation processes
        for i in range(concurrency_count):
            p = ctx.Process(
                target=_worker_create_sandbox,
                args=(git_fs.base_path, f"worker-{i}", result_queue),
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join(timeout=30.0)
            assert not p.is_alive(), "Process did not terminate within timeout"

        # 2. Collect and verify all creation results
        results: list[dict[str, Any]] = []
        for _ in range(concurrency_count):
            results.append(result_queue.get(timeout=10.0))

        assert len(results) == concurrency_count
        for res in results:
            assert res["ok"] is True, f"Worker failed: {res.get('errors')}"

        session_ids = [r["session_id"] for r in results]
        branch_names = [r["branch_name"] for r in results]
        paths = [Path(r["path"]) for r in results]

        # Verify uniqueness (no collision in IDs, branches, directories)
        assert len(set(session_ids)) == concurrency_count
        assert len(set(branch_names)) == concurrency_count
        assert len(set(paths)) == concurrency_count

        for p in paths:
            assert p.is_dir()

        # 3. Verify SQLite DB state
        db = SandboxesRepository(git_fs.base_path)
        records = db.list()
        assert len(records) >= concurrency_count
        active_ids = {r.id for r in records if r.status == SandboxStatus.ACTIVE}
        for sid in session_ids:
            assert sid in active_ids

        # 4. Launch concurrent cleanup
        cleanup_processes: list[multiprocessing.Process] = []
        for sid in session_ids:
            p = ctx.Process(
                target=_worker_cleanup_sandbox,
                args=(git_fs.base_path, sid, result_queue),
            )
            cleanup_processes.append(p)
            p.start()

        for p in cleanup_processes:
            p.join(timeout=30.0)
            assert not p.is_alive(), "Cleanup process did not terminate within timeout"

        cleanup_results: list[dict[str, Any]] = []
        for _ in range(concurrency_count):
            cleanup_results.append(result_queue.get(timeout=10.0))

        for res in cleanup_results:
            assert res["ok"] is True, f"Cleanup worker failed: {res.get('errors')}"

        # 5. Verify worktrees removed and DB records marked cleaned
        for p in paths:
            assert not p.exists()

        for sid in session_ids:
            rec = db.get(sid)
            assert rec is not None
            assert rec.status == SandboxStatus.CLEANED
