"""Tests for ``wt workflow run`` execution, CLI options, and exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from tests.helpers import GitFileSystem
from worktree.cli import app
from worktree.cli.workflow.command import workflow_run_command
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.db import RunStatus, WorkflowsDb
from worktree.core.runtime import RunOutcome

runner = CliRunner()


def _init_with_workflows(git_fs: GitFileSystem) -> Path:
    git_fs.init_repo()
    workflows_dir = git_fs.base_path / ".worktree" / "catalog" / "workflows"
    git_fs.create_workflow_file(
        "fix-tests",
        id="fix-tests",
        steps=[{"id": "step-1", "run": "echo hi"}],
    )
    scan_and_index_catalog(cwd=git_fs.base_path)
    return workflows_dir


class WorkflowRunCommandDirectTests:
    """Direct tests for workflow_run_command."""

    def test_uninitialized_worktree_exits_1(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        outcome = workflow_run_command("fix-tests", cwd=git_fs.base_path)
        assert not outcome.ok
        assert len(outcome.errors) > 0

    def test_nonexistent_workflow_exits_1(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        outcome = workflow_run_command("no-such-workflow", cwd=git_fs.base_path)
        assert not outcome.ok
        assert len(outcome.errors) > 0

    def test_valid_workflow_executes_successfully(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        outcome = workflow_run_command(
            "fix-tests",
            cwd=git_fs.base_path,
            no_sandbox=True,
            session_id="wf_test_123",
        )
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.session_id == "wf_test_123"

        out = capsys.readouterr().out
        assert "Running workflow 'fix-tests'..." in out
        assert "Workflow Run Completed:" in out
        assert "fix-tests" in out
        assert "wf_test_123" in out

        row = WorkflowsDb(git_fs.base_path).get("wf_test_123")
        assert row is not None
        assert row.status == RunStatus.COMPLETED
        assert row.workflow_name == "fix-tests"

    def test_task_blueprint_name_refused(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_task_file("sample-task", steps=[{"id": "step-1", "run": "echo hi"}])
        scan_and_index_catalog(cwd=git_fs.base_path)

        outcome = workflow_run_command("sample-task", cwd=git_fs.base_path)
        assert not outcome.ok

        out = capsys.readouterr().out
        assert "Workflow Run Failed" in out
        assert "Blueprint 'sample-task' is a task; wt workflow run requires a workflow." in out

    def test_invalid_blueprint_validation_error(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.write_file(
            ".worktree/catalog/workflows/invalid-wf.yml",
            {"version": "1.0", "name": "invalid-wf", "steps": "not-a-list"},
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        outcome = workflow_run_command("invalid-wf", cwd=git_fs.base_path)
        assert not outcome.ok

        out = capsys.readouterr().out
        assert "Workflow Run Failed" in out

    def test_corrupt_blueprint_load_error(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        (git_fs.base_path / ".worktree" / "catalog" / "workflows").mkdir(parents=True, exist_ok=True)
        (git_fs.base_path / ".worktree" / "catalog" / "workflows" / "corrupt-wf.yml").write_text(
            "version: [unclosed list",
            encoding="utf-8",
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        outcome = workflow_run_command("corrupt-wf", cwd=git_fs.base_path)
        assert not outcome.ok

        out = capsys.readouterr().out
        assert "Workflow Run Failed" in out

    def test_step_failure_aborts(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "failing-wf",
            id="failing-wf",
            steps=[
                {"id": "step-pass", "run": "echo ok"},
                {"id": "step-fail", "run": "exit 1", "on_failure": "abort"},
            ],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        outcome = workflow_run_command(
            "failing-wf",
            cwd=git_fs.base_path,
            no_sandbox=True,
            session_id="wf_fail_1",
        )
        assert not outcome.ok

        out = capsys.readouterr().out
        assert "Workflow Run Failed" in out

        row = WorkflowsDb(git_fs.base_path).get("wf_fail_1")
        assert row is not None
        assert row.status == RunStatus.FAILED
        assert row.error_message is not None

    def test_loop_step_fails_with_engine_message(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "loop-wf",
            id="loop-wf",
            steps=[
                {
                    "id": "loop-1",
                    "type": "loop",
                    "max_iterations": 3,
                    "until": ["steps.step-1.exit_code == 0"],
                    "do": [{"id": "step-1", "run": "echo hi"}],
                }
            ],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        outcome = workflow_run_command("loop-wf", cwd=git_fs.base_path, no_sandbox=True)
        assert not outcome.ok

        out = capsys.readouterr().out
        assert "Workflow Run Failed" in out
        assert "Engine.run does not execute loop steps." in out

    def test_workflow_run_cancelled_outcome(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)

        def _mock_run(self: object, *args: object, **kwargs: object) -> RunOutcome:
            return RunOutcome(
                session_id="wf_cancel_1",
                status=RunStatus.CANCELLED,
                sandbox_path=git_fs.base_path,
                error_message="Workflow cancelled by user signal.",
            )

        from worktree.core.engine import Engine

        monkeypatch.setattr(Engine, "run", _mock_run)

        outcome = workflow_run_command("fix-tests", cwd=git_fs.base_path, no_sandbox=True)
        assert not outcome.ok

        out = capsys.readouterr().out
        assert "Workflow Run Cancelled" in out
        assert "Workflow cancelled by user signal." in out

    def test_workflow_run_paused_outcome(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)

        def _mock_run(self: object, *args: object, **kwargs: object) -> RunOutcome:
            return RunOutcome(
                session_id="wf_paused_1",
                status=RunStatus.PAUSED,
                sandbox_path=git_fs.base_path,
                error_message="Workflow paused; checkpoint saved.",
            )

        from worktree.core.engine import Engine

        monkeypatch.setattr(Engine, "run", _mock_run)

        outcome = workflow_run_command("fix-tests", cwd=git_fs.base_path, no_sandbox=True)
        assert outcome.ok

        out = capsys.readouterr().out
        assert "Workflow paused; checkpoint saved." in out


class WorkflowRunCliTests:
    """CliRunner coverage for wt workflow run."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["workflow", "run", "--help"])
        assert result.exit_code == 0
        assert "Run a workflow" in result.stdout

    def test_cli_options_registration(self) -> None:
        run_cmd = get_command(app).get_command(None, "workflow").get_command(None, "run")
        opts: set[str] = set()
        for param in run_cmd.params:
            opts.update(param.opts)
            secondary = getattr(param, "secondary_opts", None) or ()
            opts.update(secondary)
        assert "--no-sandbox" in opts
        assert "--keep" in opts
        assert "--agent" in opts
        assert "--session-id" in opts
        assert "--non-interactive" in opts

    def test_valid_workflow_executes_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        result = runner.invoke(app, ["workflow", "run", "fix-tests", "--no-sandbox"])
        assert result.exit_code == 0
        assert "Workflow Run Completed:" in result.stdout
        assert "fix-tests" in result.stdout

    def test_cli_options_forwarding(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        result = runner.invoke(
            app,
            [
                "workflow",
                "run",
                "fix-tests",
                "--no-sandbox",
                "--keep",
                "--agent",
                "local",
                "--session-id",
                "wf_custom_session",
                "--non-interactive",
            ],
        )
        assert result.exit_code == 0
        assert "Workflow Run Completed:" in result.stdout

        row = WorkflowsDb(git_fs.base_path).get("wf_custom_session")
        assert row is not None
        assert row.status == RunStatus.COMPLETED

    def test_nonexistent_workflow_exits_1(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        _init_with_workflows(git_fs)
        result = runner.invoke(app, ["workflow", "run", "no-such-workflow"])
        assert result.exit_code == 1

    def test_task_blueprint_name_refused_cli(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_task_file("sample-task", steps=[{"id": "step-1", "run": "echo hi"}])
        scan_and_index_catalog(cwd=git_fs.base_path)

        result = runner.invoke(app, ["workflow", "run", "sample-task"])
        assert result.exit_code == 1
        assert "Workflow Run Failed" in result.stdout
        assert "Blueprint 'sample-task' is a task; wt workflow run requires a workflow." in result.stdout

    def test_loop_step_cli_fails(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "loop-flow",
            id="loop-flow",
            steps=[
                {
                    "id": "loop-1",
                    "type": "loop",
                    "max_iterations": 3,
                    "until": ["steps.step-1.exit_code == 0"],
                    "do": [{"id": "step-1", "run": "echo hi"}],
                }
            ],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        result = runner.invoke(app, ["workflow", "run", "loop-flow", "--no-sandbox"])
        assert result.exit_code == 1
        assert "Workflow Run Failed" in result.stdout
        assert "Engine.run does not execute loop steps." in result.stdout


class WorkflowRunInputTests:
    """Input validation and forwarding for wt workflow run."""

    def test_missing_required_input_fails(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "commit-flow",
            id="commit-flow",
            inputs={
                "message": {
                    "type": "string",
                    "required": True,
                    "aliases": ["-m", "--message"],
                }
            },
            steps=[{"id": "step-1", "run": "echo hi"}],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        result = runner.invoke(app, ["workflow", "run", "commit-flow", "--no-sandbox"])
        assert result.exit_code == 1
        assert "Workflow Run Failed" in result.stdout
        assert "Missing required input 'message'" in result.stdout

    def test_provided_input_executes_successfully(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "commit-flow",
            id="commit-flow",
            inputs={
                "message": {
                    "type": "string",
                    "required": True,
                    "aliases": ["-m", "--message"],
                }
            },
            steps=[{"id": "step-1", "run": "echo hi"}],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        result = runner.invoke(app, ["workflow", "run", "commit-flow", "-m", "hi", "--no-sandbox"])
        assert result.exit_code == 0
        assert "Workflow Run Completed:" in result.stdout

    def test_unknown_cli_args_warnings_printed(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        git_fs.init_repo()
        git_fs.create_workflow_file(
            "commit-flow",
            id="commit-flow",
            inputs={
                "message": {
                    "type": "string",
                    "required": False,
                    "default": "default msg",
                }
            },
            steps=[{"id": "step-1", "run": "echo hi"}],
        )
        scan_and_index_catalog(cwd=git_fs.base_path)

        result = runner.invoke(app, ["workflow", "run", "commit-flow", "--unknown-flag", "--no-sandbox"])
        assert result.exit_code == 0
        assert "Ignoring unrecognized option '--unknown-flag'." in result.stdout
        assert "Workflow Run Completed:" in result.stdout
