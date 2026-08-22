"""Comprehensive unit and CLI integration tests for ``wt history``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem, make_rich_output
from worktree.cli import app
from worktree.core.blueprint import BlueprintKind
from worktree.core.config.generator import generate_default_config
from worktree.core.db import RunRecord, RunsRepository, RunStatus
from worktree.core.history.models import HistoryListStatus, HistoryShowStatus
from worktree.core.history.renderers import (
    _parse_timestamp,
    format_run_duration,
    format_run_status,
    render_history_list,
    render_history_show,
)
from worktree.core.history.services import (
    HistoryListService,
    HistoryShowService,
)
from worktree.core.runtime import RunCheckpoint
from worktree.core.step import StepResult

runner = CliRunner()
_rich = make_rich_output


def _init_workspace(root: Path) -> None:
    """Initialize a valid .worktree/config.json."""
    config_file = root / ".worktree" / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    generate_default_config(config_file, project_name="test")


def _seed_run(
    root: Path,
    session_id: str,
    blueprint_name: str,
    kind: BlueprintKind,
    status: RunStatus = RunStatus.COMPLETED,
    *,
    branch_name: str = "main",
    started_at: str = "2026-08-19 01:00:00",
    completed_at: str | None = "2026-08-19 01:00:15",
    error_message: str | None = None,
    checkpoint_json: str | None = None,
) -> RunRecord:
    """Helper to insert a run row directly into RunsRepository."""
    _init_workspace(root)
    db = RunsRepository(root)
    db.create(
        session_id=session_id,
        blueprint_name=blueprint_name,
        kind=kind,
        branch_name=branch_name,
        status=RunStatus.RUNNING,
    )
    # Direct update for full field control in test fixtures
    with db.session() as session:
        from sqlmodel import select

        item = session.exec(select(RunRecord).where(RunRecord.session_id == session_id)).first()
        if item is not None:
            item.status = status
            item.started_at = started_at
            item.completed_at = completed_at
            item.error_message = error_message
            item.checkpoint_json = checkpoint_json
            session.add(item)
            session.commit()
    return db.get(session_id)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Unit tests: Renderers & Formatters
# ---------------------------------------------------------------------------


def test_format_run_status() -> None:
    """Verify status formatting includes expected Rich markup."""
    assert "green" in format_run_status(RunStatus.COMPLETED)
    assert "yellow" in format_run_status(RunStatus.PAUSED)
    assert "red" in format_run_status(RunStatus.FAILED)
    assert "dim" in format_run_status(RunStatus.CANCELLED)
    assert "cyan" in format_run_status(RunStatus.RUNNING)
    assert format_run_status("unknown") == "unknown"


def test_parse_timestamp() -> None:
    """Verify timestamp parsing handles ISO and SQLite format strings."""
    assert _parse_timestamp(None) is None
    assert _parse_timestamp("") is None
    assert _parse_timestamp("   ") is None
    assert _parse_timestamp("not-a-date") is None

    parsed_iso = _parse_timestamp("2026-08-19T01:00:00")
    assert parsed_iso is not None
    assert parsed_iso.year == 2026

    parsed_sqlite = _parse_timestamp("2026-08-19 01:00:00")
    assert parsed_sqlite is not None
    assert parsed_sqlite.hour == 1


def test_format_run_duration() -> None:
    """Verify duration calculations for seconds, minutes, and invalid inputs."""
    assert format_run_duration(None, "2026-08-19 01:00:05") == "-"
    assert format_run_duration("2026-08-19 01:00:00", None) == "-"
    assert format_run_duration("invalid", "invalid") == "-"

    # Negative duration fallback
    assert format_run_duration("2026-08-19 01:00:10", "2026-08-19 01:00:00") == "-"

    # Sub-minute duration
    duration_short = format_run_duration("2026-08-19 01:00:00", "2026-08-19 01:00:12")
    assert duration_short == "12.00s"

    # Multi-minute duration
    duration_long = format_run_duration("2026-08-19 01:00:00", "2026-08-19 01:02:30")
    assert duration_long == "2m 30.0s"


def test_render_history_list_fixed_width(fs: FileSystem) -> None:
    """Verify render_history_list produces expected columns under a fixed-width console."""
    rich_output, buffer = _rich(width=160)
    run = _seed_run(
        fs.base_path,
        "sess-12345678",
        "sample-task",
        BlueprintKind.TASK,
        RunStatus.COMPLETED,
        started_at="2026-08-19 01:00:00",
        completed_at="2026-08-19 01:00:10",
    )
    render_history_list([run], rich_output=rich_output)
    output = buffer.getvalue()
    assert "Execution History" in output
    assert "sess-12345678" in output
    assert "sample-task" in output
    assert "10.00s" in output


def test_render_history_show_fixed_width(fs: FileSystem) -> None:
    """Verify render_history_show renders session details under a fixed-width console."""
    rich_output, buffer = _rich(width=160)
    run = _seed_run(
        fs.base_path,
        "sess-show-123",
        "show-task",
        BlueprintKind.TASK,
        RunStatus.COMPLETED,
        started_at="2026-08-19 01:00:00",
        completed_at="2026-08-19 01:00:10",
    )
    render_history_show(run, rich_output=rich_output)
    output = buffer.getvalue()
    assert "Session Metadata: sess-show-123" in output
    assert "show-task" in output


# ---------------------------------------------------------------------------
# Unit tests: Collect and Command Handlers
# ---------------------------------------------------------------------------


def test_collect_history_list_not_initialized(fs: FileSystem) -> None:
    """Verify HistoryListService returns NOT_INITIALIZED when config is missing."""
    result = HistoryListService(cwd=fs.base_path / "nonexistent").collect()
    assert not result.ok
    assert result.status is HistoryListStatus.NOT_INITIALIZED


def test_collect_history_list_filters(fs: FileSystem) -> None:
    """Verify HistoryListService filters by status, kind, and limit."""
    _seed_run(fs.base_path, "run-1", "task-a", BlueprintKind.TASK, RunStatus.COMPLETED)
    _seed_run(fs.base_path, "run-2", "wf-b", BlueprintKind.WORKFLOW, RunStatus.FAILED)
    _seed_run(fs.base_path, "run-3", "task-c", BlueprintKind.TASK, RunStatus.PAUSED)

    # All runs
    all_res = HistoryListService(cwd=fs.base_path).collect()
    assert all_res.ok
    assert len(all_res.runs) == 3

    # Filter status
    failed_res = HistoryListService(status="failed", cwd=fs.base_path).collect()
    assert failed_res.ok
    assert len(failed_res.runs) == 1
    assert failed_res.runs[0].session_id == "run-2"

    # Filter kind
    wf_res = HistoryListService(kind="workflow", cwd=fs.base_path).collect()
    assert wf_res.ok
    assert len(wf_res.runs) == 1
    assert wf_res.runs[0].session_id == "run-2"

    # Limit
    limit_res = HistoryListService(limit=2, cwd=fs.base_path).collect()
    assert limit_res.ok
    assert len(limit_res.runs) == 2


def test_collect_history_show(fs: FileSystem) -> None:
    """Verify HistoryShowService returns record or classified NOT_FOUND."""
    _seed_run(fs.base_path, "run-show-1", "my-task", BlueprintKind.TASK, RunStatus.COMPLETED)

    found = HistoryShowService(session_id="run-show-1", cwd=fs.base_path).collect()
    assert found.ok
    assert found.status is HistoryShowStatus.OK
    assert found.run is not None
    assert found.run.session_id == "run-show-1"

    missing = HistoryShowService(session_id="non-existent-session", cwd=fs.base_path).collect()
    assert not missing.ok
    assert missing.status is HistoryShowStatus.NOT_FOUND


def test_collect_history_show_not_initialized(fs: FileSystem) -> None:
    """Verify HistoryShowService returns NOT_INITIALIZED when uninitialized."""
    result = HistoryShowService(session_id="session-1", cwd=fs.base_path / "nonexistent").collect()
    assert not result.ok
    assert result.status is HistoryShowStatus.NOT_INITIALIZED


def test_history_services_execute(fs: FileSystem) -> None:
    """Verify HistoryListService and HistoryShowService execute methods."""
    _seed_run(fs.base_path, "svc-run-1", "svc-task", BlueprintKind.TASK, RunStatus.COMPLETED)

    list_outcome = HistoryListService(cwd=fs.base_path).execute()
    assert list_outcome.ok
    assert len(list_outcome.runs) == 1

    show_outcome = HistoryShowService(session_id="svc-run-1", cwd=fs.base_path).execute()
    assert show_outcome.ok
    assert show_outcome.run is not None
    assert show_outcome.run.session_id == "svc-run-1"

    # Show not found
    show_missing = HistoryShowService(session_id="missing", cwd=fs.base_path).execute()
    assert not show_missing.ok
    assert show_missing.status is HistoryShowStatus.NOT_FOUND

    # Show uninitialized
    show_uninit = HistoryShowService(session_id="svc-run-1", cwd=fs.base_path / "nonexistent").execute()
    assert not show_uninit.ok
    assert show_uninit.status is HistoryShowStatus.NOT_INITIALIZED

    # List uninitialized
    list_uninit = HistoryListService(cwd=fs.base_path / "nonexistent").execute()
    assert not list_uninit.ok
    assert list_uninit.status is HistoryListStatus.NOT_INITIALIZED


# ---------------------------------------------------------------------------
# CLI Integration Tests: wt history
# ---------------------------------------------------------------------------


def test_cli_history_empty(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history' shows empty state when no runs exist."""
    _init_workspace(fs.base_path)
    monkeypatch.chdir(fs.base_path)
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "No execution history found." in result.output


def test_cli_history_table_output(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history' renders formatted table with columns and runs."""
    monkeypatch.chdir(fs.base_path)
    _seed_run(
        fs.base_path,
        "sess-12345678",
        "sample-task",
        BlueprintKind.TASK,
        RunStatus.COMPLETED,
        started_at="2026-08-19 01:00:00",
        completed_at="2026-08-19 01:00:10",
    )

    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "Execution History" in result.output
    assert "sess-12345678" in result.output
    assert "sample-task" in result.output
    assert "task" in result.output
    assert "completed" in result.output
    assert "10.00s" in result.output


def test_cli_history_filtering_options(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history' options --status, --kind, and --limit."""
    monkeypatch.chdir(fs.base_path)
    _seed_run(fs.base_path, "sess-task-ok", "task-1", BlueprintKind.TASK, RunStatus.COMPLETED)
    _seed_run(fs.base_path, "sess-task-fail", "task-2", BlueprintKind.TASK, RunStatus.FAILED)
    _seed_run(fs.base_path, "sess-wf-ok", "wf-1", BlueprintKind.WORKFLOW, RunStatus.COMPLETED)

    # Filter status: failed
    res_status = runner.invoke(app, ["history", "--status", "failed"])
    assert res_status.exit_code == 0
    assert "sess-task-fail" in res_status.output
    assert "sess-task-ok" not in res_status.output
    assert "sess-wf-ok" not in res_status.output

    # Short flag -s
    res_status_short = runner.invoke(app, ["history", "-s", "failed"])
    assert res_status_short.exit_code == 0
    assert "sess-task-fail" in res_status_short.output

    # Filter kind: workflow
    res_kind = runner.invoke(app, ["history", "--kind", "workflow"])
    assert res_kind.exit_code == 0
    assert "sess-wf-ok" in res_kind.output
    assert "sess-task-ok" not in res_kind.output

    # Short flag -k
    res_kind_short = runner.invoke(app, ["history", "-k", "workflow"])
    assert res_kind_short.exit_code == 0
    assert "sess-wf-ok" in res_kind_short.output

    # Limit
    res_limit = runner.invoke(app, ["history", "--limit", "1"])
    assert res_limit.exit_code == 0
    # Should only have 1 data row
    assert "Execution History" in res_limit.output

    # Short flag -l
    res_limit_short = runner.invoke(app, ["history", "-l", "1"])
    assert res_limit_short.exit_code == 0


def test_cli_history_uninitialized_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history' exits 1 when Worktree is not initialized."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 1
    assert "Worktree Not Initialized" in result.output


# ---------------------------------------------------------------------------
# CLI Integration Tests: wt history show
# ---------------------------------------------------------------------------


def test_cli_history_show_success(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history show <session_id>' displays session metadata panel."""
    monkeypatch.chdir(fs.base_path)
    _seed_run(
        fs.base_path,
        "show-session-1",
        "deploy-production",
        BlueprintKind.WORKFLOW,
        RunStatus.COMPLETED,
        branch_name="feature/deploy",
        started_at="2026-08-19 01:00:00",
        completed_at="2026-08-19 01:01:15",
    )

    result = runner.invoke(app, ["history", "show", "show-session-1"])
    assert result.exit_code == 0
    assert "Session Metadata: show-session-1" in result.output
    assert "deploy-production" in result.output
    assert "workflow" in result.output
    assert "feature/deploy" in result.output
    assert "completed" in result.output
    assert "1m 15.0s" in result.output


def test_cli_history_show_with_error(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history show' renders Error Details panel when error_message is present."""
    monkeypatch.chdir(fs.base_path)
    _seed_run(
        fs.base_path,
        "show-error-1",
        "faulty-task",
        BlueprintKind.TASK,
        RunStatus.FAILED,
        error_message="Step 'test-step' failed with exit code 127.",
    )

    result = runner.invoke(app, ["history", "show", "show-error-1"])
    assert result.exit_code == 0
    assert "Session Metadata: show-error-1" in result.output
    assert "Error Details" in result.output
    assert "Step 'test-step' failed with exit code 127." in result.output


def test_cli_history_show_with_checkpoint(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history show' renders Checkpoint Details panel and step results table."""
    monkeypatch.chdir(fs.base_path)
    step_res = StepResult(
        step_id="step-1",
        status="completed",
        exit_code=0,
        stdout="success",
        stderr="",
        duration_seconds=0.45,
    )
    checkpoint = RunCheckpoint(
        next_step_index=1,
        pending_step_id="step-2",
        diagnostic="Step 2 prompted user for retry",
        step_results=[step_res],
    )
    _seed_run(
        fs.base_path,
        "show-checkpoint-1",
        "paused-task",
        BlueprintKind.TASK,
        RunStatus.PAUSED,
        checkpoint_json=checkpoint.model_dump_json(),
    )

    result = runner.invoke(app, ["history", "show", "show-checkpoint-1"])
    assert result.exit_code == 0
    assert "Session Metadata: show-checkpoint-1" in result.output
    assert "Checkpoint Details" in result.output
    assert "step-2" in result.output
    assert "Step 2 prompted user for retry" in result.output
    assert "Step Results" in result.output
    assert "step-1" in result.output


def test_cli_history_show_raw_checkpoint_json_fallback(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history show' falls back to pretty JSON panel if checkpoint is non-standard."""
    monkeypatch.chdir(fs.base_path)
    raw_payload = json.dumps({"custom_field": "val123", "step": "arbitrary"})
    _seed_run(
        fs.base_path,
        "show-raw-chk-1",
        "raw-task",
        BlueprintKind.TASK,
        RunStatus.PAUSED,
        checkpoint_json=raw_payload,
    )

    result = runner.invoke(app, ["history", "show", "show-raw-chk-1"])
    assert result.exit_code == 0
    assert "Checkpoint JSON" in result.output
    assert "custom_field" in result.output


def test_cli_history_show_not_found(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history show' exits 1 when session is not found."""
    _init_workspace(fs.base_path)
    monkeypatch.chdir(fs.base_path)
    result = runner.invoke(app, ["history", "show", "nonexistent-sess"])
    assert result.exit_code == 1
    assert "Session Not Found" in result.output
    assert "Session 'nonexistent-sess' not found." in result.output


def test_cli_history_show_uninitialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'wt history show' exits 1 when Worktree is uninitialized."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["history", "show", "any-sess"])
    assert result.exit_code == 1
    assert "Worktree Not Initialized" in result.output
