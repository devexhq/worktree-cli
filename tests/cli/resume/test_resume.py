"""Comprehensive unit and CLI integration tests for ``wt resume``."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tests.helpers import (
    FileSystem,
    GitFileSystem,
    make_checkpoint,
    make_cli_context,
)
from worktree.cli import app
from worktree.core.blueprint import BlueprintKind
from worktree.core.catalog.services.inventory import scan_and_index_catalog
from worktree.core.db import RunsRepository, RunStatus, WorktreeDb
from worktree.core.engine import BlueprintResumeService
from worktree.core.runtime import FailurePromptDecision, RunCheckpoint

runner = CliRunner()


def _seed_paused_run(
    db: RunsRepository,
    session_id: str,
    blueprint_name: str,
    kind: BlueprintKind,
    checkpoint: RunCheckpoint | None = None,
    *,
    status: RunStatus = RunStatus.PAUSED,
) -> None:
    db.create(
        session_id=session_id,
        blueprint_name=blueprint_name,
        kind=kind,
        branch_name="wt/resume",
        status=RunStatus.RUNNING,
    )
    if status is RunStatus.PAUSED:
        raw = checkpoint.model_dump_json() if checkpoint is not None else make_checkpoint().model_dump_json()
        db.save_pause(session_id, raw, "paused")
    else:
        db.update_status(session_id, status)


@pytest.fixture
def mock_interactive_prompter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate an interactive user choosing to RETRY the paused step."""
    monkeypatch.setattr(
        "worktree.core.engine.services.resume.CliFailurePrompter.is_interactive",
        True,
    )
    monkeypatch.setattr(
        "worktree.core.engine.services.resume.CliFailurePrompter.prompt_step_failure",
        lambda self, *args, **kwargs: FailurePromptDecision.RETRY,
    )


class BlueprintResumeServiceTests:
    """Unit tests for BlueprintResumeService execution and session resolution."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_blueprint_resume_service_resumes_task(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify BlueprintResumeService successfully resumes a paused task session."""
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "sample-task",
            use_sandbox=False,
            steps=[
                {"id": "step-1", "run": "echo step1"},
                {"id": "step-2", "run": "echo step2", "on_failure": "prompt_user"},
            ],
        )
        _seed_paused_run(self.db.runs, "task-res-1", "sample-task", BlueprintKind.TASK)

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            session_id="task-res-1",
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
        ).execute()
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.status == RunStatus.COMPLETED
        assert outcome.run_record.kind == BlueprintKind.TASK

        record = self.db.runs.get("task-res-1")
        assert record is not None
        assert record.status == RunStatus.COMPLETED

    def test_blueprint_resume_service_resumes_workflow(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify BlueprintResumeService successfully resumes a paused workflow session."""
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        git_fs.create_workflow_file(
            "deploy-wf",
            steps=[
                {"id": "step-1", "run": "echo wf1"},
                {"id": "step-2", "run": "echo wf2", "on_failure": "prompt_user"},
            ],
        )
        scan_and_index_catalog(path=git_fs.base_path)
        git_db = WorktreeDb(path=git_fs.base_path)
        _seed_paused_run(git_db.runs, "wf-res-1", "deploy-wf", BlueprintKind.WORKFLOW)

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = BlueprintResumeService(
            session_id="wf-res-1",
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
        ).execute()
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.status == RunStatus.COMPLETED
        assert outcome.run_record.kind == BlueprintKind.WORKFLOW

        record = git_db.runs.get("wf-res-1")
        assert record is not None
        assert record.status == RunStatus.COMPLETED

    def test_blueprint_resume_service_auto_resumes_latest(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify BlueprintResumeService auto-picks the most recent paused run when session_id is omitted."""
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "task-auto",
            use_sandbox=False,
            steps=[
                {"id": "step-1", "run": "echo auto1"},
                {"id": "step-2", "run": "echo auto2", "on_failure": "prompt_user"},
            ],
        )
        _seed_paused_run(self.db.runs, "task-old", "task-auto", BlueprintKind.TASK)
        _seed_paused_run(self.db.runs, "task-new", "task-auto", BlueprintKind.TASK)

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
        ).execute()
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.session_id == "task-new"
        assert outcome.run_record.status == RunStatus.COMPLETED

    def test_blueprint_resume_service_no_paused_session_fails(
        self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify BlueprintResumeService returns failure outcome when no paused session exists."""
        monkeypatch.chdir(fs.base_path)
        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
        ).execute()
        assert not outcome.ok
        assert outcome.run_record is None
        assert any("No paused session found to resume." in err for err in outcome.errors)

    def test_blueprint_resume_service_db_get_exception_captured_in_warnings(
        self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify exceptions in _load_record during resolution are captured as warnings."""
        monkeypatch.chdir(fs.base_path)
        monkeypatch.setattr(
            self.db.runs,
            "get",
            lambda sid: (_ for _ in ()).throw(RuntimeError("DB query failed")),
        )
        monkeypatch.setattr(
            "worktree.core.engine.services.resume.Engine.resume",
            lambda *args, **kwargs: type(
                "RunOutcome",
                (),
                {"ok": False, "status": RunStatus.FAILED, "error_message": "Run failed", "warnings": []},
            )(),
        )
        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            session_id="broken-session",
            path=ctx.cwd,
            db=self.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
        ).execute()
        assert any("Failed to load run record for 'broken-session': DB query failed" in w for w in outcome.warnings)


class ResumeCliTests:
    """CLI integration tests for wt resume command."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_resume_cli_explicit_session_task(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify CLI 'wt resume <session_id>' resumes an explicit task run."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "cli-task",
            use_sandbox=False,
            steps=[
                {"id": "step-1", "run": "echo step1"},
                {"id": "step-2", "run": "echo step2", "on_failure": "prompt_user"},
            ],
        )
        _seed_paused_run(self.db.runs, "task-explicit-1", "cli-task", BlueprintKind.TASK)

        result = runner.invoke(app, ["resume", "task-explicit-1"])
        assert result.exit_code == 0
        assert "task-explicit-1" in result.output
        assert "cli-task" in result.output

    def test_resume_cli_explicit_session_workflow(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify CLI 'wt resume <session_id>' resumes an explicit workflow run."""
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        git_fs.create_workflow_file(
            "cli-wf",
            steps=[
                {"id": "step-1", "run": "echo wf1"},
                {"id": "step-2", "run": "echo wf2", "on_failure": "prompt_user"},
            ],
        )
        scan_and_index_catalog(path=git_fs.base_path)
        git_db = WorktreeDb(path=git_fs.base_path)
        _seed_paused_run(git_db.runs, "wf-explicit-1", "cli-wf", BlueprintKind.WORKFLOW)

        result = runner.invoke(app, ["resume", "wf-explicit-1"])
        assert result.exit_code == 0
        assert "wf-explicit-1" in result.output
        assert "cli-wf" in result.output

    def test_resume_cli_auto_resumes_latest_paused(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify CLI 'wt resume' with no arguments auto-resumes the latest paused session."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "latest-task",
            use_sandbox=False,
            steps=[
                {"id": "step-1", "run": "echo 1"},
                {"id": "step-2", "run": "echo 2", "on_failure": "prompt_user"},
            ],
        )
        _seed_paused_run(self.db.runs, "task-latest-1", "latest-task", BlueprintKind.TASK)

        result = runner.invoke(app, ["resume"])
        assert result.exit_code == 0
        assert "task-latest-1" in result.output

    def test_resume_cli_not_paused_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt resume' fails when the target session is not in 'paused' status."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "sample-task",
            use_sandbox=False,
            steps=[{"id": "step-1", "run": "echo 1"}],
        )
        _seed_paused_run(self.db.runs, "task-running", "sample-task", BlueprintKind.TASK, status=RunStatus.RUNNING)

        result = runner.invoke(app, ["resume", "task-running"])
        assert result.exit_code == 1
        assert "Resume Failed" in result.output
        assert "Cannot resume session 'task-running': status is 'running' (expected paused)." in result.output

    def test_resume_cli_missing_sandbox_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt resume' fails when sandbox directory was deleted."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "sandbox-task",
            use_sandbox=False,
            steps=[{"id": "step-1", "run": "echo 1"}, {"id": "step-2", "run": "echo 2"}],
        )
        checkpoint = make_checkpoint(sandbox_path="/tmp/nonexistent-sandbox-dir", use_sandbox=True)
        _seed_paused_run(self.db.runs, "task-bad-box", "sandbox-task", BlueprintKind.TASK, checkpoint=checkpoint)

        result = runner.invoke(app, ["resume", "task-bad-box"])
        assert result.exit_code == 1
        assert "Resume Failed" in result.output
        assert "no longer exists" in result.output

    def test_resume_cli_corrupt_checkpoint_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt resume' fails cleanly on corrupt checkpoint JSON."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "corrupt-task",
            use_sandbox=False,
            steps=[{"id": "step-1", "run": "echo 1"}, {"id": "step-2", "run": "echo 2"}],
        )
        self.db.runs.create(
            session_id="task-corrupt", blueprint_name="corrupt-task", kind=BlueprintKind.TASK, status=RunStatus.RUNNING
        )
        self.db.runs.save_pause("task-corrupt", "not-valid-json", "paused")

        result = runner.invoke(app, ["resume", "task-corrupt"])
        assert result.exit_code == 1
        assert "Resume Failed" in result.output
        assert "checkpoint is missing or corrupt." in result.output

    def test_resume_cli_paused_status_exits_0(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify a resumed run that pauses again exits with code 0."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "pause-again-task",
            use_sandbox=False,
            steps=[
                {"id": "step-1", "run": "echo 1"},
                {"id": "step-2", "run": "exit 1", "on_failure": "prompt_user"},
            ],
        )
        _seed_paused_run(self.db.runs, "task-pause-again", "pause-again-task", BlueprintKind.TASK)

        class _InterruptPrompter:
            is_interactive: bool = True

            def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
                raise KeyboardInterrupt

        monkeypatch.setattr(
            "worktree.core.engine.services.resume.CliFailurePrompter",
            lambda *args, **kwargs: _InterruptPrompter(),
        )

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            session_id="task-pause-again",
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            output=ctx.output,
        ).execute()
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.status == RunStatus.PAUSED

    def test_resume_cli_failed_status_exits_1(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify a resumed run that ends in failed status exits with code 1."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "fail-task",
            use_sandbox=False,
            steps=[
                {"id": "step-1", "run": "echo 1"},
                {"id": "step-2", "run": "exit 42"},
            ],
        )
        _seed_paused_run(self.db.runs, "task-fail-run", "fail-task", BlueprintKind.TASK)

        result = runner.invoke(app, ["resume", "task-fail-run"])
        assert result.exit_code == 1

    def test_resume_cli_non_interactive_aborts_prompt(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify non-interactive mode aborts failure prompts cleanly."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "non-int-task",
            use_sandbox=False,
            steps=[
                {"id": "step-1", "run": "echo 1"},
                {"id": "step-2", "run": "exit 1", "on_failure": "prompt_user"},
            ],
        )
        _seed_paused_run(self.db.runs, "task-non-int", "non-int-task", BlueprintKind.TASK)

        result = runner.invoke(app, ["resume", "task-non-int", "--non-interactive"])
        assert result.exit_code == 1
        assert "Resume Failed" in result.output

    def test_resume_cli_cancelled_status(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt resume' handles cancelled status cleanly."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        fs.create_task_file(
            "cancel-task",
            use_sandbox=False,
            steps=[
                {"id": "step-1", "run": "echo 1"},
                {"id": "step-2", "run": "echo 2", "on_failure": "prompt_user"},
            ],
        )
        _seed_paused_run(self.db.runs, "task-cancel", "cancel-task", BlueprintKind.TASK)

        monkeypatch.setattr(
            "worktree.core.engine.services.resume.Engine.resume",
            lambda *args, **kwargs: type(
                "RunOutcome",
                (),
                {"ok": False, "status": RunStatus.CANCELLED, "error_message": "Cancelled by user.", "warnings": []},
            )(),
        )

        result = runner.invoke(app, ["resume", "task-cancel"])
        assert result.exit_code == 1
        assert "Resume Cancelled" in result.output
