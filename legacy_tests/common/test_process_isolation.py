"""Unit tests for subprocess process group isolation and cascading tree termination."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worktree.common.process import (
    ProcessRegistry,
    get_isolated_process_kwargs,
    is_process_group_alive,
    run_isolated_process,
    terminate_process_tree,
)


class ProcessIsolationUnitTests:
    """Unit tests for common process isolation utilities."""

    def test_get_isolated_process_kwargs_posix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        kwargs = get_isolated_process_kwargs()
        assert kwargs == {"start_new_session": True}

    def test_get_isolated_process_kwargs_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        kwargs = get_isolated_process_kwargs()
        assert kwargs == {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)}

    def test_is_process_group_alive_current_process(self) -> None:
        if sys.platform == "win32" or not hasattr(os, "getpgid"):
            pytest.skip("POSIX only")
        pgid = os.getpgid(os.getpid())
        assert is_process_group_alive(pgid) is True

    def test_is_process_group_alive_nonexistent(self) -> None:
        if sys.platform == "win32" or not hasattr(os, "killpg"):
            pytest.skip("POSIX only")
        assert is_process_group_alive(9999999) is False

    def test_terminate_process_tree_already_exited(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"])
        proc.wait(timeout=5)
        # Should execute cleanly without errors on dead process
        terminate_process_tree(proc, grace_seconds=0.1)

    def test_terminate_process_tree_pid_only(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            **get_isolated_process_kwargs(),
        )
        pid = proc.pid
        try:
            terminate_process_tree(pid, grace_seconds=0.1)
            proc.wait(timeout=5)
            assert proc.poll() is not None
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_run_isolated_process_success(self, tmp_path: Path) -> None:
        completed = run_isolated_process(
            [sys.executable, "-c", "import sys; sys.stdout.write('hello'); sys.stderr.write('world')"],
            cwd=tmp_path,
            text=True,
        )
        assert completed.returncode == 0
        assert completed.stdout == "hello"
        assert completed.stderr == "world"

    def test_run_isolated_process_with_input(self) -> None:
        completed = run_isolated_process(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"],
            input_data="test input",
            text=True,
        )
        assert completed.returncode == 0
        assert completed.stdout == "TEST INPUT"

    def test_run_isolated_process_timeout(self) -> None:
        with pytest.raises(subprocess.TimeoutExpired):
            run_isolated_process(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout_seconds=0.2,
                grace_seconds=0.1,
            )

    def test_run_isolated_process_exception_cleans_up(self) -> None:
        with patch("subprocess.Popen.communicate", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                run_isolated_process(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                )


class ProcessRegistryTests:
    """Unit tests for ProcessRegistry active process tracking."""

    def test_registry_lifecycle(self) -> None:
        registry = ProcessRegistry()
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345

        assert len(registry) == 0
        registry.register(proc, pgid=12345)
        assert len(registry) == 1

        registry.unregister(proc)
        assert len(registry) == 0

    def test_registry_terminate_all(self) -> None:
        registry = ProcessRegistry()
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            **get_isolated_process_kwargs(),
        )
        try:
            registry.register(proc, pgid=proc.pid)
            assert len(registry) == 1
            registry.terminate_all(grace_seconds=0.1)
            assert len(registry) == 0
            proc.wait(timeout=5)
            assert proc.poll() is not None
        finally:
            if proc.poll() is None:
                proc.kill()


class WindowsProcessTreeTerminationTests:
    """Tests for Windows process tree termination fallback paths."""

    def test_terminate_windows_tree_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 9999
        mock_proc.wait.side_effect = [Exception("still running"), None]

        with patch("subprocess.run") as mock_run:
            terminate_process_tree(mock_proc, grace_seconds=0.1)
            mock_proc.terminate.assert_called_once()
            mock_run.assert_called_once_with(
                ["taskkill", "/PID", "9999", "/T", "/F"],
                capture_output=True,
                timeout=5.0,
                check=False,
            )
            mock_proc.kill.assert_called_once()
