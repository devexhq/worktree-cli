"""Concurrency integration tests for GitSandboxManager."""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import Any

from tests.helpers import GitFileSystem
from worktree.core.db import SandboxesRepository, SandboxStatus
from worktree.core.sandbox import Sandbox


def _worker_create_sandbox(
    repo_path: Path,
    name: str,
    result_queue: multiprocessing.Queue[dict[str, Any]],
) -> None:
    """Worker process that instantiates a repository/manager and creates a sandbox."""
    try:
        db = SandboxesRepository(repo_path)
        sandbox = Sandbox(path=repo_path, db=db)
        result = sandbox.create(name=name)
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
    result_queue: multiprocessing.Queue[dict[str, Any]],
) -> None:
    """Worker process that cleans up a sandbox by session id."""
    try:
        db = SandboxesRepository(repo_path)
        record = db.get(session_id)
        if record is None:
            result_queue.put({"ok": False, "errors": [f"Record {session_id} not found"]})
            return

        sandbox = Sandbox(path=repo_path, db=db)
        warnings = sandbox.cleanup(record)
        result_queue.put({"ok": True, "warnings": warnings})
    except Exception as exc:
        result_queue.put({"ok": False, "errors": [str(exc)]})


def _run_and_wait_processes(processes: list[Any], timeout: float = 30.0) -> None:
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=timeout)
        assert not p.is_alive(), "Process did not terminate within timeout"


def _drain_queue(queue: Any, count: int, timeout: float = 10.0) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for _ in range(count):
        res = queue.get(timeout=timeout)
        assert res["ok"] is True, f"Worker failed: {res.get('errors')}"
        results.append(res)
    return results


def _verify_cleaned(db: SandboxesRepository, paths: list[Path], session_ids: list[str]) -> None:
    for p in paths:
        assert not p.exists()
    for sid in session_ids:
        rec = db.get(sid)
        assert rec is not None
        assert rec.status == SandboxStatus.CLEANED


class TestConcurrentSandboxOperations:
    """Integration tests verifying cross-process concurrency safety on sandboxes."""

    def test_concurrent_sandbox_creation_and_cleanup(self, git_fs: GitFileSystem) -> None:
        git_fs.init_repo()
        git_fs.create_config_file(sandbox={"max_active_sandboxes": 10})

        ctx = multiprocessing.get_context("spawn")
        result_queue = ctx.Queue()

        concurrency_count = 3

        # 1. Launch 3 concurrent sandbox creation processes
        processes = [
            ctx.Process(
                target=_worker_create_sandbox,
                args=(git_fs.base_path, f"worker-{i}", result_queue),
            )
            for i in range(concurrency_count)
        ]
        _run_and_wait_processes(processes)

        # 2. Collect and verify all creation results
        results = _drain_queue(result_queue, concurrency_count)
        session_ids = [r["session_id"] for r in results]
        branch_names = [r["branch_name"] for r in results]
        paths = [Path(r["path"]) for r in results]

        # Verify uniqueness (no collision in IDs, branches, directories)
        assert len(set(session_ids)) == concurrency_count
        assert len(set(branch_names)) == concurrency_count
        assert len(set(paths)) == concurrency_count
        assert all(p.is_dir() for p in paths)

        # 3. Verify SQLite DB state
        db = SandboxesRepository(git_fs.base_path)
        active_ids = {r.id for r in db.list() if r.status == SandboxStatus.ACTIVE}
        assert all(sid in active_ids for sid in session_ids)

        # 4. Launch concurrent cleanup
        cleanup_processes = [
            ctx.Process(
                target=_worker_cleanup_sandbox,
                args=(git_fs.base_path, sid, result_queue),
            )
            for sid in session_ids
        ]
        _run_and_wait_processes(cleanup_processes)
        _drain_queue(result_queue, concurrency_count)

        # 5. Verify worktrees removed and DB records marked cleaned
        _verify_cleaned(db, paths, session_ids)
