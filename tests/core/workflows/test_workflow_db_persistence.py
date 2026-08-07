"""Tests for workflow run persistence in SQLite workflows table during run_workflow_iteration."""

from __future__ import annotations

from pathlib import Path

import pytest

from getworktree.core.config.generator import generate_default_config
from getworktree.core.db import RunStatus, WorkflowsDb
from getworktree.core.git_sandbox import (
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
)
from getworktree.core.workflows.models import (
    WorkflowDefinition,
)
from getworktree.core.workflows.runner import run_workflow_iteration
from getworktree.core.workflows.trigger import TriggerRunResult, TriggerRunStatus


def _init_config(repo: Path) -> None:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    generate_default_config(config_path, project_name=repo.name)


def _make_dummy_workflow(name: str = "test-workflow") -> WorkflowDefinition:
    return WorkflowDefinition(
        version="1.0",
        name=name,
        description="Dummy test workflow",
    )


def test_run_workflow_iteration_records_workflow_passed(git_repo: Path) -> None:
    _init_config(git_repo)
    workflow = _make_dummy_workflow("passed-workflow")
    dummy_session = SandboxSession(
        session_id="wf-pass-101",
        target_branch="wt/passed-workflow",
        sandbox_path=git_repo / ".worktree" / "sandboxes" / "wf-pass-101",
        base_commit="HEAD",
        created_at="2026-08-05 12:00:00",
    )

    def mock_create_sandbox() -> SandboxCreateResult:
        return SandboxCreateResult(status=SandboxCreateStatus.OK, session=dummy_session)

    def mock_run_trigger(*args: object, **kwargs: object) -> TriggerRunResult:
        return TriggerRunResult(
            status=TriggerRunStatus.PASSED,
            command="echo",
            args=["hello"],
            cwd=git_repo,
            exit_code=0,
            duration_ms=10,
        )

    result = run_workflow_iteration(
        workflow=workflow,
        cwd=git_repo,
        create_sandbox_fn=mock_create_sandbox,
        run_trigger_fn=mock_run_trigger,
        cleanup_sandbox_fn=lambda s: None,
    )

    assert result.session_id == "wf-pass-101"

    rec = WorkflowsDb(git_repo).get("wf-pass-101")
    assert rec is not None
    assert rec.session_id == "wf-pass-101"
    assert rec.workflow_name == "passed-workflow"
    assert rec.branch_name == "wt/passed-workflow"
    assert rec.status == RunStatus.COMPLETED
    assert rec.completed_at is not None
    assert rec.error_message is None

    all_runs = WorkflowsDb(git_repo).list()
    assert len(all_runs) >= 1
    assert any(r.session_id == "wf-pass-101" for r in all_runs)


def test_run_workflow_iteration_records_workflow_failed(git_repo: Path) -> None:
    _init_config(git_repo)
    workflow = _make_dummy_workflow("failed-workflow")
    dummy_session = SandboxSession(
        session_id="wf-fail-202",
        target_branch="wt/failed-workflow",
        sandbox_path=git_repo / ".worktree" / "sandboxes" / "wf-fail-202",
        base_commit="HEAD",
        created_at="2026-08-05 12:00:00",
    )

    def mock_create_sandbox() -> SandboxCreateResult:
        return SandboxCreateResult(status=SandboxCreateStatus.OK, session=dummy_session)

    def mock_run_trigger(*args: object, **kwargs: object) -> TriggerRunResult:
        return TriggerRunResult(
            status=TriggerRunStatus.FAILED,
            command="echo",
            args=["fail"],
            cwd=git_repo,
            exit_code=1,
            duration_ms=10,
            errors=["Test failure"],
        )

    result = run_workflow_iteration(
        workflow=workflow,
        cwd=git_repo,
        caller_max_attempts=1,
        create_sandbox_fn=mock_create_sandbox,
        run_trigger_fn=mock_run_trigger,
        cleanup_sandbox_fn=lambda s: None,
    )

    assert result.session_id == "wf-fail-202"

    rec = WorkflowsDb(git_repo).get("wf-fail-202")
    assert rec is not None
    assert rec.session_id == "wf-fail-202"
    assert rec.workflow_name == "failed-workflow"
    assert rec.status == RunStatus.FAILED
    assert rec.completed_at is not None
    assert rec.error_message is not None


def test_run_workflow_iteration_fault_tolerant_db_write_error(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_config(git_repo)
    workflow = _make_dummy_workflow("error-workflow")
    dummy_session = SandboxSession(
        session_id="wf-err-303",
        target_branch="wt/error-workflow",
        sandbox_path=git_repo / ".worktree" / "sandboxes" / "wf-err-303",
        base_commit="HEAD",
        created_at="2026-08-05 12:00:00",
    )

    def mock_create_sandbox() -> SandboxCreateResult:
        return SandboxCreateResult(status=SandboxCreateStatus.OK, session=dummy_session)

    def mock_run_trigger(*args: object, **kwargs: object) -> TriggerRunResult:
        return TriggerRunResult(
            status=TriggerRunStatus.PASSED,
            command="echo",
            args=["hello"],
            cwd=git_repo,
            exit_code=0,
            duration_ms=10,
        )

    # Monkeypatch WorkflowsDb.insert to raise an Exception to verify fault tolerance
    def bad_insert(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Database locked")

    monkeypatch.setattr(WorkflowsDb, "insert", bad_insert)

    result = run_workflow_iteration(
        workflow=workflow,
        cwd=git_repo,
        create_sandbox_fn=mock_create_sandbox,
        run_trigger_fn=mock_run_trigger,
        cleanup_sandbox_fn=lambda s: None,
    )

    assert result.session_id == "wf-err-303"
    assert any("Failed to record workflow run start" in w for w in result.warnings)
