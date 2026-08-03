"""Tests for ``wt loop run`` UX and exit codes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.loop.renderers import (
    exit_code_for_status,
    format_attempt_block,
    format_progress_event,
    format_run_summary,
)
from getworktree.core.config.generator import generate_default_config
from getworktree.core.loops.runner import (
    AttemptRecord,
    LoopFinalStatus,
    LoopRunResult,
)
from getworktree.core.loops.seeder import seed_starter_loops

runner = CliRunner()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return tmp_path


def _init_with_loops(repo: Path) -> None:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    assert generate_default_config(config_path, project_name=repo.name).ok
    assert seed_starter_loops(repo / ".worktree" / "loops").ok


def _fixture_result(
    status: LoopFinalStatus,
    *,
    stop_reason: str,
    attempts: list[AttemptRecord] | None = None,
    max_attempts: int = 5,
    retained: bool = False,
    sandbox_path: Path | None = None,
) -> LoopRunResult:
    return LoopRunResult(
        status=status,
        session_id="sbx_a1b2c3d4",
        loop_name="fix-tests",
        sandbox_path=sandbox_path,
        attempts=attempts
        or [
            AttemptRecord(
                attempt=1,
                trigger_status="failed",
                trigger_exit_code=1,
                trigger_duration_ms=12400,
                agent_status="proposed_patch",
                agent_duration_ms=3100,
                patch_status="applied",
                patch_touched_files=["a.py", "b.py", "c.py"],
            ),
            AttemptRecord(
                attempt=2,
                trigger_status="passed",
                trigger_exit_code=0,
                trigger_duration_ms=10100,
            ),
        ],
        stop_reason=stop_reason,
        max_attempts=max_attempts,
        sandbox_retained=retained,
    )


class ExitCodeTests:
    def test_mapping(self) -> None:
        assert exit_code_for_status(LoopFinalStatus.PASSED) == 0
        assert exit_code_for_status(LoopFinalStatus.FAILED) == 1
        assert exit_code_for_status(LoopFinalStatus.UNFIXABLE) == 2
        assert exit_code_for_status(LoopFinalStatus.ABORTED) == 130


class RendererTests:
    def test_progress_event_lines(self) -> None:
        start = format_progress_event(
            "session_start",
            {
                "loop_name": "fix-tests",
                "session_id": "sbx_deadbeef",
                "max_attempts": 5,
            },
        )
        assert start is not None
        assert "Running loop fix-tests" in start
        assert "Session:  sbx_deadbeef" in start
        assert "Budget:   5 attempt(s)" in start

        attempt = format_progress_event(
            "attempt_start", {"attempt": 2, "max_attempts": 5}
        )
        assert attempt == "Attempt 2/5\n"

        trigger_start = format_progress_event(
            "trigger_start",
            {"command": "pytest", "args": ["-q"], "timeout_seconds": 60},
        )
        assert trigger_start == "  Trigger: running (pytest -q)...\n"

        trigger = format_progress_event(
            "trigger",
            {"status": "failed", "exit_code": 1, "duration_ms": 12400},
        )
        assert trigger == "  Trigger: failed (exit 1) 12.4s\n"

        agent_start = format_progress_event(
            "agent_start",
            {"provider": "local", "mode": "fix_failure"},
        )
        assert agent_start == "  Agent:   running (local/fix_failure)...\n"

        agent = format_progress_event(
            "agent",
            {"status": "proposed_patch", "duration_ms": 3100},
        )
        assert agent == "  Agent:   proposed_patch 3.1s\n"

        patch_start = format_progress_event("patch_start", {"attempt": 1})
        assert patch_start == "  Patch:   applying...\n"

        patch = format_progress_event(
            "patch",
            {"status": "applied", "touched_files": ["a.py", "b.py"]},
        )
        assert patch == "  Patch:   applied (2 files)\n"
        assert format_progress_event("unknown", {}) is None

    def test_attempt_block_failed_then_agent_patch(self) -> None:
        rec = AttemptRecord(
            attempt=1,
            trigger_status="failed",
            trigger_exit_code=1,
            trigger_duration_ms=12400,
            agent_status="proposed_patch",
            agent_duration_ms=3100,
            patch_status="applied",
            patch_touched_files=["a.py", "b.py", "c.py"],
        )
        text = format_attempt_block(rec, max_attempts=5)
        assert "Attempt 1/5" in text
        assert "Trigger: failed (exit 1) 12.4s" in text
        assert "Agent:   proposed_patch 3.1s" in text
        assert "Patch:   applied (3 files)" in text

    def test_attempt_block_passed_only(self) -> None:
        rec = AttemptRecord(
            attempt=2,
            trigger_status="passed",
            trigger_duration_ms=10100,
        )
        text = format_attempt_block(rec, max_attempts=5)
        assert "Attempt 2/5" in text
        assert "Trigger: passed 10.1s" in text
        assert "Agent:" not in text

    def test_summary_passed(self, tmp_path: Path) -> None:
        result = _fixture_result(LoopFinalStatus.PASSED, stop_reason="trigger_passed")
        text = format_run_summary(result, cwd=tmp_path)
        assert "── Loop run summary" in text
        assert "Loop:       fix-tests" in text
        assert "Status:     PASSED" in text
        assert "Session:    sbx_a1b2c3d4" in text
        assert "Attempts:   2/5" in text
        assert "Stop:       trigger_passed" in text
        assert "Sandbox:    removed" in text
        assert "Artifacts:  .worktree/sessions/sbx_a1b2c3d4" in text
        assert "Next:" in text
        assert "wt history show sbx_a1b2c3d4" in text
        assert "wt diff sbx_a1b2c3d4" in text

    def test_summary_failed_retained(self, tmp_path: Path) -> None:
        sbx = tmp_path / ".worktree" / "sandboxes" / "sbx_a1b2c3d4"
        sbx.mkdir(parents=True)
        result = _fixture_result(
            LoopFinalStatus.FAILED,
            stop_reason="max_attempts_exhausted",
            attempts=[
                AttemptRecord(attempt=i, trigger_status="failed") for i in range(1, 6)
            ],
            max_attempts=5,
            retained=True,
            sandbox_path=sbx,
        )
        text = format_run_summary(result, cwd=tmp_path)
        assert "Status:     FAILED" in text
        assert "Attempts:   5/5" in text
        assert "Sandbox:    kept at .worktree/sandboxes/sbx_a1b2c3d4" in text
        assert "re-run: wt loop run fix-tests" in text

    def test_summary_aborted_and_unfixable(self, tmp_path: Path) -> None:
        aborted = _fixture_result(
            LoopFinalStatus.ABORTED,
            stop_reason="user_abort",
            attempts=[AttemptRecord(attempt=1, trigger_status="failed")],
        )
        text = format_run_summary(aborted, cwd=tmp_path)
        assert "Status:     ABORTED" in text
        assert "wt prune" in text

        unf = _fixture_result(
            LoopFinalStatus.UNFIXABLE,
            stop_reason="agent_unfixable",
            attempts=[
                AttemptRecord(
                    attempt=1,
                    trigger_status="failed",
                    agent_status="unfixable",
                )
            ],
        )
        text2 = format_run_summary(unf, cwd=tmp_path)
        assert "Status:     UNFIXABLE" in text2
        assert "adjust loop context/trigger" in text2


class LoopRunCliTests:
    def test_help_text(self) -> None:
        # Assert registration via Click metadata. Do not parse Rich --help text:
        # narrow CI terminals wrap/truncate option names and the docstring.
        result = runner.invoke(app, ["loop", "run", "--help"])
        assert result.exit_code == 0

        run_cmd = get_command(app).get_command(None, "loop").get_command(None, "run")
        assert run_cmd.help == "Run a loop in an isolated git worktree sandbox."
        opts: set[str] = set()
        for param in run_cmd.params:
            opts.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            opts.update(secondary)
        assert "--max-attempts" in opts
        assert "--keep" in opts
        assert "--no-keep" in opts
        assert "--approve-each" in opts
        assert "--no-approve-each" in opts

    def test_resolve_failure(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        result = runner.invoke(app, ["loop", "run", "does-not-exist"])
        assert result.exit_code == 1
        assert "Loop Run Failed" in result.stdout
        assert "── Loop run summary" not in result.stdout

    def test_passed_with_monkeypatched_controller(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        fixture = _fixture_result(LoopFinalStatus.PASSED, stop_reason="trigger_passed")

        def fake_run(**_kwargs):
            return fixture

        monkeypatch.setattr(
            "getworktree.commands.loop.command.run_loop_iteration",
            fake_run,
        )
        result = runner.invoke(app, ["loop", "run", "fix-tests"])
        assert result.exit_code == 0
        assert "Status:     PASSED" in result.stdout
        assert "Attempt 1/5" in result.stdout
        assert "Trigger: failed (exit 1) 12.4s" in result.stdout
        assert "Stop:       trigger_passed" in result.stdout

    def test_live_progress_streams_and_skips_duplicate_attempts(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        fixture = _fixture_result(LoopFinalStatus.PASSED, stop_reason="trigger_passed")

        def fake_run(**kwargs):
            on_event = kwargs.get("on_event")
            assert on_event is not None
            on_event(
                "session_start",
                {
                    "loop_name": "fix-tests",
                    "session_id": "sbx_a1b2c3d4",
                    "max_attempts": 5,
                },
            )
            on_event("attempt_start", {"attempt": 1, "max_attempts": 5})
            on_event(
                "trigger_start",
                {"command": "pytest", "args": [], "timeout_seconds": 600},
            )
            on_event(
                "trigger",
                {"status": "failed", "exit_code": 1, "duration_ms": 12400},
            )
            on_event(
                "agent_start",
                {"provider": "local", "mode": "fix_failure"},
            )
            on_event(
                "agent",
                {"status": "proposed_patch", "duration_ms": 3100},
            )
            on_event("patch_start", {"attempt": 1})
            on_event(
                "patch",
                {
                    "status": "applied",
                    "touched_files": ["a.py", "b.py", "c.py"],
                },
            )
            on_event("attempt_start", {"attempt": 2, "max_attempts": 5})
            on_event(
                "trigger_start",
                {"command": "pytest", "args": [], "timeout_seconds": 600},
            )
            on_event(
                "trigger",
                {"status": "passed", "exit_code": 0, "duration_ms": 10100},
            )
            return fixture

        monkeypatch.setattr(
            "getworktree.commands.loop.command.run_loop_iteration",
            fake_run,
        )
        result = runner.invoke(app, ["loop", "run", "fix-tests"])
        assert result.exit_code == 0
        out = result.stdout
        assert "Running loop fix-tests" in out
        assert "Trigger: running (pytest)..." in out
        assert "Agent:   running (local/fix_failure)..." in out
        assert "Patch:   applying..." in out
        assert "Trigger: failed (exit 1) 12.4s" in out
        assert "Status:     PASSED" in out
        # Attempt header once per attempt (live only), not duplicated in summary.
        assert out.count("Attempt 1/5") == 1
        assert out.count("Attempt 2/5") == 1
        assert out.index("Trigger: running (pytest)...") < out.index(
            "── Loop run summary"
        )

    def test_failed_exit_code(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        fixture = _fixture_result(
            LoopFinalStatus.FAILED,
            stop_reason="repeat_failure_signature",
            attempts=[
                AttemptRecord(attempt=1, trigger_status="failed", trigger_exit_code=1)
            ],
            max_attempts=5,
        )
        monkeypatch.setattr(
            "getworktree.commands.loop.command.run_loop_iteration",
            lambda **_k: fixture,
        )
        result = runner.invoke(app, ["loop", "run", "fix-tests"])
        assert result.exit_code == 1
        assert "Status:     FAILED" in result.stdout
        assert "Stop:       repeat_failure_signature" in result.stdout

    def test_unfixable_exit_code(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        fixture = _fixture_result(
            LoopFinalStatus.UNFIXABLE,
            stop_reason="agent_unfixable",
            attempts=[
                AttemptRecord(
                    attempt=1,
                    trigger_status="failed",
                    agent_status="unfixable",
                )
            ],
        )
        monkeypatch.setattr(
            "getworktree.commands.loop.command.run_loop_iteration",
            lambda **_k: fixture,
        )
        result = runner.invoke(app, ["loop", "run", "fix-tests"])
        assert result.exit_code == 2
        assert "Status:     UNFIXABLE" in result.stdout

    def test_aborted_exit_code(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        fixture = _fixture_result(
            LoopFinalStatus.ABORTED,
            stop_reason="user_abort",
            attempts=[],
            max_attempts=5,
        )
        monkeypatch.setattr(
            "getworktree.commands.loop.command.run_loop_iteration",
            lambda **_k: fixture,
        )
        result = runner.invoke(app, ["loop", "run", "fix-tests"])
        assert result.exit_code == 130
        assert "Status:     ABORTED" in result.stdout

    def test_missing_config(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["loop", "run", "fix-tests"])
        assert result.exit_code == 1
        assert "Loop Run Failed" in result.stdout
