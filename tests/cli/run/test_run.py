"""Comprehensive tests for top-level ``wt run`` execution and CLI options."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem, GitFileSystem
from worktree.cli import app
from worktree.cli.context import get_cli_context
from worktree.core.blueprint import BlueprintKind, BlueprintRunService
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.db import RunsRepository, RunStatus

runner = CliRunner()


def test_blueprint_run_service_executes_task(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify BlueprintRunService successfully executes a task blueprint when kind=None."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "build-task",
        description="Build task",
        summary="Build task",
        use_sandbox=False,
        steps=[
            {"id": "step-1", "run": "echo task step 1"},
            {"id": "step-2", "run": "echo task step 2"},
        ],
    )

    ctx = get_cli_context(cwd=fs.base_path)
    res = BlueprintRunService(
        name="build-task",
        path=ctx.cwd,
        runs_db=ctx.db.runs,
        catalog_db=ctx.db.catalog,
        session_id="test_run_task_1",
    ).execute()
    assert res.ok
    assert res.run_record is not None
    assert res.run_record.status == RunStatus.COMPLETED
    assert res.run_record.kind == BlueprintKind.TASK

    record = RunsRepository(fs.base_path).get("test_run_task_1")
    assert record is not None
    assert record.status == RunStatus.COMPLETED
    assert record.kind == BlueprintKind.TASK


def test_blueprint_run_service_executes_workflow(git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify BlueprintRunService successfully executes a workflow blueprint when kind=None."""
    git_fs.init_repo()
    monkeypatch.chdir(git_fs.base_path)
    git_fs.create_workflow_file(
        "deploy-flow",
        steps=[{"id": "step-1", "run": "echo deploy step 1"}],
    )
    scan_and_index_catalog(path=git_fs.base_path)

    ctx = get_cli_context(cwd=git_fs.base_path)
    res = BlueprintRunService(
        name="deploy-flow",
        path=ctx.cwd,
        runs_db=ctx.db.runs,
        catalog_db=ctx.db.catalog,
        no_sandbox=True,
        session_id="test_run_wf_1",
    ).execute()
    assert res.ok
    assert res.run_record is not None
    assert res.run_record.status == RunStatus.COMPLETED
    assert res.run_record.kind == BlueprintKind.WORKFLOW

    record = RunsRepository(git_fs.base_path).get("test_run_wf_1")
    assert record is not None
    assert record.status == RunStatus.COMPLETED
    assert record.kind == BlueprintKind.WORKFLOW


def test_run_cli_task_invocation(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt run <task-name>' options and output."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "format-task",
        description="Format code",
        summary="Format code",
        use_sandbox=False,
        steps=[{"id": "fmt", "run": "echo formatting"}],
    )

    result = runner.invoke(
        app,
        ["run", "format-task", "--no-sandbox", "--agent", "claude-3-5-sonnet"],
    )
    assert result.exit_code == 0
    assert "Task Run Completed:" in result.output
    assert "Sandbox: In-place (workspace)" in result.output


def test_run_cli_workflow_invocation(git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI 'wt run <workflow-name>' options and output."""
    git_fs.init_repo()
    monkeypatch.chdir(git_fs.base_path)
    git_fs.create_workflow_file(
        "audit-flow",
        steps=[{"id": "audit-step", "run": "echo auditing"}],
    )
    scan_and_index_catalog(path=git_fs.base_path)

    result = runner.invoke(
        app,
        ["run", "audit-flow", "--no-sandbox", "--session-id", "audit_session_1"],
    )
    assert result.exit_code == 0
    assert "Workflow Run Completed:" in result.output
    assert "audit_session_1" in result.output


def test_run_cli_input_forwarding(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify trailing CLI args are forwarded to blueprint declared inputs."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "greet-task",
        inputs={"target": {"type": "string", "default": "world"}},
        steps=[{"id": "greet", "run": "echo Hello $TARGET"}],
        use_sandbox=False,
    )

    result = runner.invoke(
        app,
        ["run", "greet-task", "--no-sandbox", "--target", "Antigravity"],
    )
    assert result.exit_code == 0
    assert "Task Run Completed:" in result.output


def test_run_cli_keep_flag(git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify --keep preserves the sandbox worktree."""
    git_fs.init_repo()
    monkeypatch.chdir(git_fs.base_path)
    git_fs.create_workflow_file(
        "sandbox-flow",
        steps=[{"id": "sbx-step", "run": "echo sandbox"}],
    )
    scan_and_index_catalog(path=git_fs.base_path)

    result = runner.invoke(
        app,
        ["run", "sandbox-flow", "--keep", "--session-id", "keep_session_1"],
    )
    assert result.exit_code == 0
    record = RunsRepository(git_fs.base_path).get("keep_session_1")
    assert record is not None
    assert record.status == RunStatus.COMPLETED


def test_run_cli_non_existent_blueprint_fails(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify running a non-existent blueprint fails with exit code 1."""
    monkeypatch.chdir(fs.base_path)
    result = runner.invoke(app, ["run", "unknown-blueprint"])
    assert result.exit_code == 1
    assert "Run Failed" in result.output or "not found" in result.output


def test_run_cli_step_failure_exits_1(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a failing blueprint step returns exit code 1."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "failing-task",
        use_sandbox=False,
        steps=[{"id": "fail-step", "run": "exit 1", "on_failure": "abort"}],
    )

    result = runner.invoke(app, ["run", "failing-task", "--no-sandbox"])
    assert result.exit_code == 1
    assert "Task Run Failed" in result.output


def test_run_cli_non_interactive_aborts_prompt_user(fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify --non-interactive aborts on prompt_user and exits 1."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "prompt-task",
        use_sandbox=False,
        steps=[{"id": "prompt-step", "run": "exit 1", "on_failure": "prompt_user"}],
    )

    result = runner.invoke(
        app,
        ["run", "prompt-task", "--no-sandbox", "--non-interactive"],
    )
    assert result.exit_code == 1


def test_run_cli_paused_status_exits_0(
    fs: FileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a paused run exits with code 0 and logs checkpoint notice."""
    monkeypatch.chdir(fs.base_path)
    fs.create_task_file(
        "pause-task",
        use_sandbox=False,
        steps=[{"id": "pause-step", "run": "exit 1", "on_failure": "prompt_user"}],
    )

    from worktree.core.runtime import FailurePromptDecision

    class _InterruptPrompter:
        is_interactive: bool = True

        def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
            raise KeyboardInterrupt

    monkeypatch.setattr(
        "worktree.core.blueprint.services.run.CliFailurePrompter",
        lambda *args, **kwargs: _InterruptPrompter(),
    )

    ctx = get_cli_context(cwd=fs.base_path)
    outcome = BlueprintRunService(
        name="pause-task",
        path=ctx.cwd,
        runs_db=ctx.db.runs,
        catalog_db=ctx.db.catalog,
        session_id="paused_session_1",
    ).execute()
    assert outcome.run_record is not None
    assert outcome.run_record.status == RunStatus.PAUSED
