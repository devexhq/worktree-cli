"""Comprehensive tests for top-level ``wt run`` execution and CLI options."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import FileSystem, GitFileSystem, make_cli_context
from worktree.cli import app
from worktree.cli.run.commands.root import run_command
from worktree.core.blueprint import BlueprintKind
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.db import RunStatus, WorktreeDb
from worktree.core.engine import BlueprintRunService

runner = CliRunner()


class BlueprintRunServiceTests:
    """Unit tests for BlueprintRunService direct execution."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_blueprint_run_service_executes_task(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
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

        ctx = make_cli_context(cwd=fs.base_path)
        res = BlueprintRunService(
            name="build-task",
            path=ctx.cwd,
            runs_db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
            session_id="test_run_task_1",
        ).execute()
        assert res.ok
        assert res.run_record is not None
        assert res.run_record.status == RunStatus.COMPLETED
        assert res.run_record.kind == BlueprintKind.TASK

        record = self.db.runs.get("test_run_task_1")
        assert record is not None
        assert record.status == RunStatus.COMPLETED
        assert record.kind == BlueprintKind.TASK

    def test_blueprint_run_service_executes_workflow(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify BlueprintRunService successfully executes a workflow blueprint when kind=None."""
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        git_fs.create_workflow_file(
            "deploy-flow",
            steps=[{"id": "step-1", "run": "echo deploy step 1"}],
        )
        scan_and_index_catalog(path=git_fs.base_path)

        ctx = make_cli_context(cwd=git_fs.base_path)
        res = BlueprintRunService(
            name="deploy-flow",
            path=ctx.cwd,
            runs_db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
            no_sandbox=True,
            session_id="test_run_wf_1",
        ).execute()
        assert res.ok
        assert res.run_record is not None
        assert res.run_record.status == RunStatus.COMPLETED
        assert res.run_record.kind == BlueprintKind.WORKFLOW

        record = WorktreeDb(path=git_fs.base_path).runs.get("test_run_wf_1")
        assert record is not None
        assert record.status == RunStatus.COMPLETED
        assert record.kind == BlueprintKind.WORKFLOW

    def test_blueprint_run_service_reconciles_stale_runs(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify BlueprintRunService reconciles dead running runs before starting execution."""
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "quick-task",
            description="Quick task",
            summary="Quick task",
            use_sandbox=False,
            steps=[{"id": "step-1", "run": "echo done"}],
        )

        self.db.runs.create(
            session_id="dead_prior_run",
            blueprint_name="old_task",
            kind="task",
            pid=9999999,
        )

        ctx = make_cli_context(cwd=fs.base_path)
        res = BlueprintRunService(
            name="quick-task",
            path=ctx.cwd,
            runs_db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
            session_id="new_run_1",
        ).execute()
        assert res.ok

        stale_rec = self.db.runs.get("dead_prior_run")
        assert stale_rec is not None
        assert stale_rec.status == RunStatus.FAILED


class RunCliTests:
    """CLI integration tests for wt run command."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_run_cli_task_invocation(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt run <task-name>' options and output."""
        fs.create_config_file()
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

    def test_run_cli_workflow_invocation(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
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

    def test_run_cli_input_forwarding(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify trailing CLI args are forwarded to blueprint declared inputs."""
        fs.create_config_file()
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

    def test_run_cli_keep_flag(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
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
        record = WorktreeDb(path=git_fs.base_path).runs.get("keep_session_1")
        assert record is not None
        assert record.status == RunStatus.COMPLETED

    def test_run_cli_non_existent_blueprint_fails(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify running a non-existent blueprint fails with exit code 1."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        result = runner.invoke(app, ["run", "unknown-blueprint"])
        assert result.exit_code == 1
        assert "Run Failed" in result.output or "not found" in result.output

    def test_run_cli_step_failure_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify a failing blueprint step returns exit code 1."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "failing-task",
            use_sandbox=False,
            steps=[{"id": "fail-step", "run": "exit 1", "on_failure": "abort"}],
        )

        result = runner.invoke(app, ["run", "failing-task", "--no-sandbox"])
        assert result.exit_code == 1
        assert "Task Run Failed" in result.output

    def test_run_cli_non_interactive_aborts_prompt_user(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify --non-interactive aborts on prompt_user and exits 1."""
        fs.create_config_file()
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
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify a paused run exits with code 0 and logs checkpoint notice."""
        fs.create_config_file()
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
            "worktree.core.engine.services.run.CliFailurePrompter",
            lambda *args, **kwargs: _InterruptPrompter(),
        )

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintRunService(
            name="pause-task",
            path=ctx.cwd,
            runs_db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
            session_id="paused_session_1",
        ).execute()
        assert outcome.run_record is not None
        assert outcome.run_record.status == RunStatus.PAUSED


class RunCommandDirectTests:
    """Unit tests for run_command Typer-unaware handler."""

    def test_run_command_executes_blueprint(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify run_command executes a blueprint via context."""
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "direct-task",
            use_sandbox=False,
            steps=[{"id": "step-1", "run": "echo direct"}],
        )

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = run_command(
            ctx,
            name="direct-task",
            no_sandbox=True,
            session_id="direct_run_1",
        )
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.status == RunStatus.COMPLETED
