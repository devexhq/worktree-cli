"""Unit tests for worktree.common.lock."""

from __future__ import annotations

import multiprocessing
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worktree.common.lock import (
    LockTimeoutError,
    WorkspaceLock,
    _cleanup_registered_locks,
    _try_lock_windows,
    _unlock_file_descriptor,
    resolve_lock_file_path,
)


def _child_hold_lock(lock_dir: Path, hold_seconds: float, ready_event: multiprocessing.Event) -> None:
    """Helper process that holds WorkspaceLock for a fixed duration."""
    with WorkspaceLock(lock_dir, timeout_seconds=5.0):
        ready_event.set()
        time.sleep(hold_seconds)


def _child_acquire_with_timeout(
    lock_dir: Path,
    timeout_seconds: float,
    result_queue: multiprocessing.Queue,  # type: ignore[reportMissingTypeArgument]
) -> None:
    """Helper process that tries to acquire WorkspaceLock and captures outcome."""
    try:
        with WorkspaceLock(lock_dir, timeout_seconds=timeout_seconds):
            result_queue.put({"success": True})
    except LockTimeoutError as exc:
        result_queue.put({"success": False, "error": str(exc)})
    except Exception as exc:
        result_queue.put({"success": False, "error": f"Unexpected: {exc}"})


class TestWorkspaceLock:
    """Tests for WorkspaceLock context manager."""

    def test_resolve_lock_file_path_root_dir(self, tmp_path: Path) -> None:
        lock_file = resolve_lock_file_path(tmp_path)
        assert lock_file == tmp_path.resolve() / ".worktree" / ".lock"

    def test_resolve_lock_file_path_worktree_dir(self, tmp_path: Path) -> None:
        worktree_dir = tmp_path / ".worktree"
        lock_file = resolve_lock_file_path(worktree_dir)
        assert lock_file == worktree_dir.resolve() / ".lock"

    def test_basic_acquire_and_release(self, tmp_path: Path) -> None:
        lock = WorkspaceLock(tmp_path)
        assert not lock.lock_path.exists()

        with lock:
            assert lock.lock_path.exists()
            content = lock.lock_path.read_text(encoding="utf-8").strip()
            assert content == str(os.getpid())

        # Can acquire again after release
        with WorkspaceLock(tmp_path):
            assert lock.lock_path.exists()

    def test_reentrant_nesting_same_process(self, tmp_path: Path) -> None:
        lock1 = WorkspaceLock(tmp_path)
        lock2 = WorkspaceLock(tmp_path)

        with lock1:
            with lock2:
                assert lock2._is_nested is True
                assert lock1.lock_path.exists()
            assert lock1._file_descriptor is not None

        # Lock is fully released after outer block exits
        assert lock1._file_descriptor is None

    def test_exception_releases_lock(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="Intentional failure"):
            with WorkspaceLock(tmp_path):
                raise RuntimeError("Intentional failure")

        # Must be acquirable immediately after exception
        with WorkspaceLock(tmp_path):
            assert True

    def test_cross_process_contention_timeout(self, tmp_path: Path) -> None:
        ctx = multiprocessing.get_context("spawn")
        ready_event = ctx.Event()
        result_queue = ctx.Queue()

        # Start holder process holding for 1.5s
        p1 = ctx.Process(target=_child_hold_lock, args=(tmp_path, 1.5, ready_event))
        p1.start()

        try:
            assert ready_event.wait(timeout=5.0), "Holder process failed to acquire lock"

            # Start waiter with 0.3s timeout
            p2 = ctx.Process(target=_child_acquire_with_timeout, args=(tmp_path, 0.3, result_queue))
            p2.start()
            p2.join(timeout=5.0)

            result = result_queue.get(timeout=3.0)
            assert result["success"] is False
            assert "Timed out waiting for workspace lock" in result["error"]
            assert str(p1.pid) in result["error"]
        finally:
            p1.join(timeout=5.0)

    def test_cross_process_queueing_success(self, tmp_path: Path) -> None:
        ctx = multiprocessing.get_context("spawn")
        ready_event = ctx.Event()
        result_queue = ctx.Queue()

        # Holder process holds for 0.4s
        p1 = ctx.Process(target=_child_hold_lock, args=(tmp_path, 0.4, ready_event))
        p1.start()

        try:
            assert ready_event.wait(timeout=5.0), "Holder process failed to acquire lock"

            # Waiter with 3.0s timeout should wait and succeed
            p2 = ctx.Process(target=_child_acquire_with_timeout, args=(tmp_path, 3.0, result_queue))
            p2.start()
            p2.join(timeout=5.0)

            result = result_queue.get(timeout=3.0)
            assert result["success"] is True
        finally:
            p1.join(timeout=5.0)

    def test_on_wait_callback_fires_on_contention(self, tmp_path: Path) -> None:
        ctx = multiprocessing.get_context("spawn")
        ready_event = ctx.Event()
        called: list[tuple[Path, str | None, float]] = []

        def on_wait(path: Path, holder_pid: str | None, timeout: float) -> None:
            called.append((path, holder_pid, timeout))

        # Start holder holding lock for 0.6s
        p1 = ctx.Process(target=_child_hold_lock, args=(tmp_path, 0.6, ready_event))
        p1.start()

        try:
            assert ready_event.wait(timeout=5.0), "Holder process failed to acquire lock"

            # Waiter with on_wait callback
            with WorkspaceLock(tmp_path, timeout_seconds=3.0, on_wait=on_wait) as lock:
                assert lock.lock_path.exists()

            assert len(called) == 1
            lock_path, holder_pid, timeout_val = called[0]
            assert lock_path == resolve_lock_file_path(tmp_path)
            assert holder_pid == str(p1.pid)
            assert timeout_val == 3.0
        finally:
            p1.join(timeout=5.0)

    def test_default_on_wait_callback_fires_on_contention(self, tmp_path: Path) -> None:
        ctx = multiprocessing.get_context("spawn")
        ready_event = ctx.Event()
        called: list[tuple[Path, str | None, float]] = []

        def default_on_wait(path: Path, holder_pid: str | None, timeout: float) -> None:
            called.append((path, holder_pid, timeout))

        WorkspaceLock.set_default_on_wait(default_on_wait)
        try:
            p1 = ctx.Process(target=_child_hold_lock, args=(tmp_path, 0.6, ready_event))
            p1.start()

            try:
                assert ready_event.wait(timeout=5.0), "Holder process failed to acquire lock"

                # Constructor omits on_wait, so default should fire
                with WorkspaceLock(tmp_path, timeout_seconds=3.0) as lock:
                    assert lock.lock_path.exists()

                assert len(called) == 1
                assert called[0][0] == resolve_lock_file_path(tmp_path)
                assert called[0][1] == str(p1.pid)
                assert called[0][2] == 3.0
            finally:
                p1.join(timeout=5.0)
        finally:
            WorkspaceLock.reset_default_on_wait()

    def test_explicit_on_wait_overrides_default(self, tmp_path: Path) -> None:
        default_called: list[tuple[Path, str | None, float]] = []
        explicit_called: list[tuple[Path, str | None, float]] = []

        def default_cb(p: Path, h: str | None, t: float) -> None:
            default_called.append((p, h, t))

        def explicit_cb(p: Path, h: str | None, t: float) -> None:
            explicit_called.append((p, h, t))

        WorkspaceLock.set_default_on_wait(default_cb)
        try:
            lock = WorkspaceLock(tmp_path, on_wait=explicit_cb)
            assert lock.on_wait is explicit_cb
        finally:
            WorkspaceLock.reset_default_on_wait()

    def test_cleanup_registered_locks(self, tmp_path: Path) -> None:
        lock = WorkspaceLock(tmp_path)
        lock.acquire()
        assert lock._file_descriptor is not None

        _cleanup_registered_locks()
        # After cleanup, lock registry is empty
        with WorkspaceLock(tmp_path):
            assert True

    def test_mock_windows_lock(self, tmp_path: Path) -> None:
        mock_msvcrt = MagicMock()
        mock_msvcrt.LK_NBLCK = 1
        mock_msvcrt.LK_UNLCK = 2

        with (
            patch("worktree.common.lock.msvcrt", mock_msvcrt, create=True),
            patch("worktree.common.lock.sys.platform", "win32"),
        ):
            lock_path = tmp_path / ".worktree" / ".lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                assert _try_lock_windows(fd) is True
                mock_msvcrt.locking.assert_called_with(fd, 1, 1)
                _unlock_file_descriptor(fd)
                mock_msvcrt.locking.assert_called_with(fd, 2, 1)
            finally:
                os.close(fd)
