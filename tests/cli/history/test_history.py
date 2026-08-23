"""Comprehensive unit and CLI integration tests for ``wt history``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem, make_rich_output, make_run
from worktree.cli import app
from worktree.core.blueprint import BlueprintKind
from worktree.core.config.generator import generate_default_config
from worktree.core.db import RunsRepository, RunStatus
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


def _init_workspace(root: Path) -> None:
    """Initialize a valid .worktree/config.json."""
    config_file = root / ".worktree" / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    generate_default_config(config_file, project_name="test")


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
    rich_output, buffer = make_rich_output(width=160)
    run = make_run(
        root=fs.base_path,
        session_id="sess-12345678",
        blueprint_name="sample-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
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
    rich_output, buffer = make_rich_output(width=160)
    run = make_run(
        root=fs.base_path,
        session_id="sess-show-123",
        blueprint_name="show-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
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
    path = fs.base_path / "nonexistent"
    result = HistoryListService(path=path, db=RunsRepository(path)).collect()
    assert not result.ok
    assert result.status is HistoryListStatus.NOT_INITIALIZED


def test_collect_history_list_filters(fs: FileSystem) -> None:
    """Verify HistoryListService filters by status, kind, and limit."""
    make_run(
        root=fs.base_path,
        session_id="run-1",
        blueprint_name="task-a",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
    )
    make_run(
        root=fs.base_path,
        session_id="run-2",
        blueprint_name="wf-b",
        kind=BlueprintKind.WORKFLOW,
        status=RunStatus.FAILED,
    )
    make_run(
        root=fs.base_path, session_id="run-3", blueprint_name="task-c", kind=BlueprintKind.TASK, status=RunStatus.PAUSED
    )

    # All runs
    all_res = HistoryListService(path=fs.base_path, db=RunsRepository(fs.base_path)).collect()
    assert all_res.ok
    assert len(all_res.runs) == 3

    # Filter status
    failed_res = HistoryListService(path=fs.base_path, db=RunsRepository(fs.base_path), status="failed").collect()
    assert failed_res.ok
    assert len(failed_res.runs) == 1
    assert failed_res.runs[0].session_id == "run-2"

    # Filter kind
    wf_res = HistoryListService(path=fs.base_path, db=RunsRepository(fs.base_path), kind="workflow").collect()
    assert wf_res.ok
    assert len(wf_res.runs) == 1
    assert wf_res.runs[0].session_id == "run-2"

    # Limit
    limit_res = HistoryListService(path=fs.base_path, db=RunsRepository(fs.base_path), limit=2).collect()
    assert limit_res.ok
    assert len(limit_res.runs) == 2


def test_collect_history_show(fs: FileSystem) -> None:
    """Verify HistoryShowService returns record or classified NOT_FOUND."""
    make_run(
        root=fs.base_path,
        session_id="run-show-1",
        blueprint_name="my-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
    )

    found = HistoryShowService(session_id="run-show-1", path=fs.base_path, db=RunsRepository(fs.base_path)).collect()
    assert found.ok
    assert found.status is HistoryShowStatus.OK
    assert found.run is not None
    assert found.run.session_id == "run-show-1"

    missing = HistoryShowService(
        session_id="non-existent-session", path=fs.base_path, db=RunsRepository(fs.base_path)
    ).collect()
    assert not missing.ok
    assert missing.status is HistoryShowStatus.NOT_FOUND


def test_collect_history_show_not_initialized(fs: FileSystem) -> None:
    """Verify HistoryShowService returns NOT_INITIALIZED when uninitialized."""
    path = fs.base_path / "nonexistent"
    result = HistoryShowService(session_id="session-1", path=path, db=RunsRepository(path)).collect()
    assert not result.ok
    assert result.status is HistoryShowStatus.NOT_INITIALIZED


def test_history_services_execute(fs: FileSystem) -> None:
    """Verify HistoryListService and HistoryShowService execute methods."""
    make_run(
        root=fs.base_path,
        session_id="svc-run-1",
        blueprint_name="svc-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
    )

    list_outcome = HistoryListService(path=fs.base_path, db=RunsRepository(fs.base_path)).execute()
    assert list_outcome.ok
    assert len(list_outcome.runs) == 1

    show_outcome = HistoryShowService(
        session_id="svc-run-1", path=fs.base_path, db=RunsRepository(fs.base_path)
    ).execute()
    assert show_outcome.ok
    assert show_outcome.run is not None
    assert show_outcome.run.session_id == "svc-run-1"

    # Show not found
    show_missing = HistoryShowService(
        session_id="missing", path=fs.base_path, db=RunsRepository(fs.base_path)
    ).execute()
    assert not show_missing.ok
    assert show_missing.status is HistoryShowStatus.NOT_FOUND

    # Show uninitialized
    path_missing = fs.base_path / "nonexistent"
    show_uninit = HistoryShowService(
        session_id="svc-run-1", path=path_missing, db=RunsRepository(path_missing)
    ).execute()
    assert not show_uninit.ok
    assert show_uninit.status is HistoryShowStatus.NOT_INITIALIZED

    # List uninitialized
    list_uninit = HistoryListService(path=path_missing, db=RunsRepository(path_missing)).execute()
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
    make_run(
        root=fs.base_path,
        session_id="sess-12345678",
        blueprint_name="sample-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
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
    make_run(
        root=fs.base_path,
        session_id="sess-task-ok",
        blueprint_name="task-1",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
    )
    make_run(
        root=fs.base_path,
        session_id="sess-task-fail",
        blueprint_name="task-2",
        kind=BlueprintKind.TASK,
        status=RunStatus.FAILED,
    )
    make_run(
        root=fs.base_path,
        session_id="sess-wf-ok",
        blueprint_name="wf-1",
        kind=BlueprintKind.WORKFLOW,
        status=RunStatus.COMPLETED,
    )

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
    make_run(
        root=fs.base_path,
        session_id="show-session-1",
        blueprint_name="deploy-production",
        kind=BlueprintKind.WORKFLOW,
        status=RunStatus.COMPLETED,
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
    make_run(
        root=fs.base_path,
        session_id="show-error-1",
        blueprint_name="faulty-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.FAILED,
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
    make_run(
        root=fs.base_path,
        session_id="show-checkpoint-1",
        blueprint_name="paused-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.PAUSED,
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
    make_run(
        root=fs.base_path,
        session_id="show-raw-chk-1",
        blueprint_name="raw-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.PAUSED,
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
