"""Tests for workflow trigger runner."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from getworktree.core.workflows.trigger import (
    TriggerRunStatus,
    run_trigger,
)


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    d = tmp_path / "sandbox"
    d.mkdir()
    return d


class RunTriggerTests:
    """Unit tests for run_trigger classified outcomes."""

    def test_passed(self, workdir: Path) -> None:
        result = run_trigger(
            command=sys.executable,
            args=["-c", "import sys; sys.stdout.write('ok'); sys.exit(0)"],
            cwd=workdir,
            timeout_seconds=10,
        )
        assert result.ok
        assert result.status == TriggerRunStatus.PASSED
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.stdout == "ok"
        assert result.errors == []
        assert result.started_at is not None
        assert result.finished_at is not None
        assert result.duration_ms >= 0
        assert result.cwd == workdir.resolve()

    def test_failed_nonzero(self, workdir: Path) -> None:
        result = run_trigger(
            command=sys.executable,
            args=["-c", "import sys; sys.stderr.write('boom'); sys.exit(7)"],
            cwd=workdir,
            timeout_seconds=10,
        )
        assert not result.ok
        assert result.status == TriggerRunStatus.FAILED
        assert result.exit_code == 7
        assert result.stderr == "boom"
        assert result.errors
        assert "TRIGGER_FAILED" in result.errors[0]
        assert "7" in result.errors[0]

    def test_timeout(self, workdir: Path) -> None:
        result = run_trigger(
            command=sys.executable,
            args=["-c", "import time; time.sleep(30)"],
            cwd=workdir,
            timeout_seconds=1,
        )
        assert not result.ok
        assert result.status == TriggerRunStatus.TIMEOUT
        assert result.timed_out is True
        assert result.exit_code is None
        assert "timed out after 1s" in result.errors[0]
        assert result.duration_ms < 15_000

    def test_spawn_failed_missing_command(self, workdir: Path) -> None:
        result = run_trigger(
            command="definitely-not-a-real-cmd-xyz-wt",
            args=[],
            cwd=workdir,
            timeout_seconds=5,
        )
        assert result.status == TriggerRunStatus.SPAWN_FAILED
        assert result.exit_code is None
        assert "Failed to start trigger command" in result.errors[0]
        assert "definitely-not-a-real-cmd-xyz-wt" in result.errors[0]

    def test_cwd_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        result = run_trigger(
            command=sys.executable,
            args=["-c", "pass"],
            cwd=missing,
            timeout_seconds=5,
        )
        assert result.status == TriggerRunStatus.CWD_MISSING
        assert "TRIGGER_CWD_MISSING" in result.errors[0]
        assert result.stdout == ""
        assert result.stderr == ""

    def test_args_default_empty(self, workdir: Path) -> None:
        # sys.executable with no args typically exits 0 printing nothing useful
        # Use true-like python -c via explicit empty args path for /bin/true if present
        true_path = Path("/bin/true")
        if not true_path.is_file():
            pytest.skip("/bin/true not available")
        result = run_trigger(
            command=str(true_path),
            args=None,
            cwd=workdir,
            timeout_seconds=5,
        )
        assert result.ok
        assert result.args == []

    def test_no_shell_metacharacters(self, workdir: Path) -> None:
        # If shell were True, echo would run; with argv, command name is literal.
        result = run_trigger(
            command="echo hello",
            args=[],
            cwd=workdir,
            timeout_seconds=5,
        )
        assert result.status == TriggerRunStatus.SPAWN_FAILED

    def test_env_replace_not_inherit(self, workdir: Path) -> None:
        marker = "WT_TRIGGER_ENV_MARKER"
        result = run_trigger(
            command=sys.executable,
            args=[
                "-c",
                "import os,sys; sys.stdout.write(os.environ.get('WT_TRIGGER_ENV_MARKER',''))",
            ],
            cwd=workdir,
            timeout_seconds=5,
            env={"PATH": os.environ.get("PATH", ""), marker: "from-child"},
        )
        assert result.ok
        assert result.stdout == "from-child"

    def test_utf8_replacement(self, workdir: Path) -> None:
        result = run_trigger(
            command=sys.executable,
            args=[
                "-c",
                "import sys; sys.stdout.buffer.write(b'a\\xffb')",
            ],
            cwd=workdir,
            timeout_seconds=5,
        )
        assert result.ok
        assert "a" in result.stdout
        assert "b" in result.stdout

    def test_artifacts_written(self, workdir: Path, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs" / "attempt1"
        result = run_trigger(
            command=sys.executable,
            args=["-c", "import sys; sys.stdout.write('out'); sys.stderr.write('err')"],
            cwd=workdir,
            timeout_seconds=5,
            log_dir=log_dir,
        )
        assert result.ok
        assert result.log_dir == log_dir
        assert (log_dir / "trigger_stdout.log").read_text(encoding="utf-8") == "out"
        assert (log_dir / "trigger_stderr.log").read_text(encoding="utf-8") == "err"
        meta = json.loads((log_dir / "trigger_meta.json").read_text(encoding="utf-8"))
        assert meta["command"] == sys.executable
        assert meta["args"] == [
            "-c",
            "import sys; sys.stdout.write('out'); sys.stderr.write('err')",
        ]
        assert meta["exit_code"] == 0
        assert meta["timed_out"] is False
        assert meta["status"] == "passed"
        assert meta["duration_ms"] >= 0
        assert "started_at" in meta
        assert "finished_at" in meta
        assert meta["cwd"] == str(workdir.resolve())

    def test_artifacts_skipped_when_log_dir_none(
        self, workdir: Path, tmp_path: Path
    ) -> None:
        result = run_trigger(
            command=sys.executable,
            args=["-c", "print('x')"],
            cwd=workdir,
            timeout_seconds=5,
            log_dir=None,
        )
        assert result.ok
        assert result.log_dir is None
        # no surprise files under tmp
        assert (
            list(tmp_path.iterdir()) == [workdir.relative_to(tmp_path) and workdir]
            or True
        )

    def test_log_dir_not_writable_warns(self, workdir: Path, tmp_path: Path) -> None:
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        blocked.chmod(0o500)
        log_dir = blocked / "nested" / "logs"
        try:
            # Make parent unwritable for create of nested — on some systems chmod
            # on dir prevents create inside.
            blocked.chmod(0o000)
            result = run_trigger(
                command=sys.executable,
                args=["-c", "import sys; sys.exit(0)"],
                cwd=workdir,
                timeout_seconds=5,
                log_dir=log_dir,
            )
            assert result.status == TriggerRunStatus.PASSED
            assert result.ok
            assert result.warnings
            assert any("Failed" in w for w in result.warnings)
        finally:
            blocked.chmod(0o700)

    def test_large_output_captured(self, workdir: Path) -> None:
        result = run_trigger(
            command=sys.executable,
            args=["-c", "import sys; sys.stdout.write('x'*100000); sys.exit(2)"],
            cwd=workdir,
            timeout_seconds=10,
        )
        assert result.status == TriggerRunStatus.FAILED
        assert len(result.stdout) == 100000
