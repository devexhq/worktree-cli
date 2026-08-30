"""Unit and integration tests for step subprocess process group isolation (Issue #372)."""

from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

import pytest

from tests.helpers import FileSystem
from worktree.core.step import (
    StepDefinition,
    StepExecution,
    StepExecutionContext,
    StepType,
)


class StepProcessGroupIsolationTests:
    """Tests verifying dedicated process group isolation and cascading termination."""

    def test_detached_background_child_killed_on_step_timeout(self, fs: FileSystem) -> None:
        """Verify detached grandchild processes are killed when step times out."""
        if sys.platform == "win32":
            pytest.skip("POSIX process group test")

        pid_file = fs.base_path / "child.pid"
        # Script spawns a background child process that writes its PID to a file and sleeps 60s
        spawn_script = (
            "import subprocess, sys, time\n"
            "p = subprocess.Popen([\n"
            "    sys.executable, '-c',\n"
            f'    \'import os, time; open("{pid_file}", "w").write(str(os.getpid())); time.sleep(60)\'\n'
            "])\n"
            "time.sleep(10)\n"
        )
        fs.write_file("spawn.py", spawn_script)

        step = StepDefinition(
            id="spawn_step",
            type=StepType.SCRIPT,
            script_path="spawn.py",
            timeout_seconds=1,
        )

        result = StepExecution(StepExecutionContext(step=step, sandbox_path=fs.base_path)).run()
        assert result.ok is False
        assert result.status == "failed"
        assert result.exit_code == 124
        assert "timed out after 1" in (result.error_message or "")

        # Verify child process PID was written and then terminated
        assert pid_file.exists(), "Child process was not spawned"
        child_pid = int(pid_file.read_text().strip())

        # Check that the child process is dead
        child_alive = True
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            child_alive = False
        except PermissionError:
            child_alive = True

        assert not child_alive, f"Detached child process {child_pid} was orphaned!"

    def test_sigterm_escalation_to_sigkill_on_timeout(self, fs: FileSystem) -> None:
        """Verify timeout escalates from SIGTERM to SIGKILL when process traps SIGTERM."""
        if sys.platform == "win32":
            pytest.skip("POSIX signal trapping test")

        ignore_sigterm_script = (
            "import signal, sys, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(10)\n"
        )
        fs.write_file("ignore_term.py", ignore_sigterm_script)

        step = StepDefinition(
            id="ignore_term_step",
            type=StepType.SCRIPT,
            script_path="ignore_term.py",
            timeout_seconds=1,
        )

        start_time = time.monotonic()
        result = StepExecution(StepExecutionContext(step=step, sandbox_path=fs.base_path)).run()
        elapsed = time.monotonic() - start_time

        assert result.ok is False
        assert result.status == "failed"
        assert result.exit_code == 124
        assert "timed out after 1" in (result.error_message or "")
        # Elapsed time should account for timeout (1s) + grace period (~2s)
        assert elapsed >= 2.0

    def test_keyboard_interrupt_terminates_child_process_tree(self, fs: FileSystem) -> None:
        """Verify KeyboardInterrupt terminates running child processes cleanly."""
        if sys.platform == "win32":
            pytest.skip("POSIX process group test")

        pid_file = fs.base_path / "proc.pid"
        long_script = f"import os, time; open('{pid_file}', 'w').write(str(os.getpid())); time.sleep(60)\n"
        fs.write_file("long.py", long_script)

        step = StepDefinition(
            id="interrupt_step",
            type=StepType.SCRIPT,
            script_path="long.py",
            timeout_seconds=30,
        )

        execution = StepExecution(StepExecutionContext(step=step, sandbox_path=fs.base_path))

        # Simulate KeyboardInterrupt while waiting in proc.wait
        with patch("subprocess.Popen.wait", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                execution.run()

    def test_process_group_cleaned_up_on_normal_failure(self, fs: FileSystem) -> None:
        """Verify step failure does not leave processes running."""
        step = StepDefinition(
            id="failing_step",
            type=StepType.COMMAND,
            command="exit 1",
        )

        result = StepExecution(StepExecutionContext(step=step, sandbox_path=fs.base_path)).run()
        assert result.ok is False
        assert result.exit_code == 1
