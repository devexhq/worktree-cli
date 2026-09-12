"""Comprehensive unit and CLI integration tests for ``wt resume``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import (
    BlueprintHelper,
    CatalogHelper,
    FileSystem,
    GitFileSystem,
    RunFactory,
    make_checkpoint,
    make_cli_context,
    make_run_outcome,
)
from worktree.cli import app
from worktree.cli.resume.commands.root import resume_command
from worktree.core.db import RunStatus, WorktreeDb
from worktree.core.engine import BlueprintResumeService
from worktree.core.runtime import FailurePromptDecision, LoopPromptDecision

runner = CliRunner()


def _save_resume_blueprint(
    catalog: CatalogHelper,
    *,
    key: str = "resume",
    **overrides: object,
) -> BlueprintHelper:
    """Save a valid blueprint definition and return its transparent test handle."""
    blueprint = catalog.blueprint(key=key, **overrides)
    catalog.save(blueprint)
    return blueprint


@pytest.fixture
def resume_blueprint(catalog: CatalogHelper) -> BlueprintHelper:
    """Save and return the canonical blueprint for successful resume tests."""
    return _save_resume_blueprint(catalog)


class _RetryPrompter:
    """Test prompter that always returns RETRY for prompt_user steps."""

    is_interactive: bool = True

    def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
        return FailurePromptDecision.RETRY

    def prompt_loop_max_iterations(self, **kwargs: object) -> LoopPromptDecision:
        return LoopPromptDecision.ABORT


@pytest.fixture
def mock_interactive_prompter(monkeypatch: pytest.MonkeyPatch) -> _RetryPrompter:
    """Simulate an interactive user choosing to RETRY the paused step."""
    prompter = _RetryPrompter()
    monkeypatch.setattr(
        "worktree.cli.resume.commands.root.DispatcherFailurePrompter",
        lambda *args, **kwargs: prompter,
    )
    return prompter


class BlueprintResumeServiceTests:
    """Unit tests for BlueprintResumeService execution and session resolution."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem, catalog: CatalogHelper, runs: RunFactory) -> None:
        fs.create_config_file()
        self.db = WorktreeDb(path=fs.base_path)
        self.catalog = catalog
        self.runs = runs

    def test_blueprint_resume_service_resumes_task(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: _RetryPrompter,
        resume_blueprint: BlueprintHelper,
    ) -> None:
        """Verify BlueprintResumeService successfully resumes a paused blueprint session."""
        monkeypatch.chdir(fs.base_path)
        self.runs.create_paused(session_id="task-res-1", blueprint=resume_blueprint.catalog_item)

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            session_id="task-res-1",
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            failure_prompter=mock_interactive_prompter,
        ).execute()
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.status == RunStatus.COMPLETED

        record = self.db.runs.get("task-res-1")
        assert record is not None
        assert record.status == RunStatus.COMPLETED

    def test_blueprint_resume_service_resumes_workflow(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: _RetryPrompter,
    ) -> None:
        """Verify BlueprintResumeService successfully resumes a paused workflow session."""
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        blueprint = _save_resume_blueprint(CatalogHelper(git_fs))
        git_db = WorktreeDb(path=git_fs.base_path)
        RunFactory(git_db.runs).create_paused(session_id="wf-res-1", blueprint=blueprint.catalog_item)

        ctx = make_cli_context(cwd=git_fs.base_path)
        outcome = BlueprintResumeService(
            session_id="wf-res-1",
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            failure_prompter=mock_interactive_prompter,
        ).execute()
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.status == RunStatus.COMPLETED

        record = git_db.runs.get("wf-res-1")
        assert record is not None
        assert record.status == RunStatus.COMPLETED

    def test_blueprint_resume_service_auto_resumes_latest(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: _RetryPrompter,
        resume_blueprint: BlueprintHelper,
    ) -> None:
        """Verify BlueprintResumeService auto-picks the most recent paused run when session_id is omitted."""
        monkeypatch.chdir(fs.base_path)
        self.runs.create_paused(session_id="task-old", blueprint=resume_blueprint.catalog_item)
        self.runs.create_paused(session_id="task-new", blueprint=resume_blueprint.catalog_item)

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            failure_prompter=mock_interactive_prompter,
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
        ).execute()
        assert not outcome.ok
        assert outcome.run_record is None
        assert any("No paused session found to resume." in err for err in outcome.errors)

    def test_blueprint_resume_service_db_get_exception_captured_in_warnings(
        self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify exceptions in _load_record during resolution are captured as warnings."""
        monkeypatch.chdir(fs.base_path)

        def raise_db_query_error(_session_id: str) -> None:
            raise RuntimeError("DB query failed")

        monkeypatch.setattr(self.db.runs, "get", raise_db_query_error)
        monkeypatch.setattr(
            "worktree.core.engine.services.resume.Engine.resume",
            lambda *_args, **_kwargs: make_run_outcome(
                status=RunStatus.FAILED,
                errors=["Run failed"],
                sandbox_path=Path(".worktree/sandboxes/sbx-run-1"),
            ),
        )
        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            session_id="broken-session",
            path=ctx.cwd,
            db=self.db.runs,
            catalog_db=ctx.db.catalog,
        ).execute()
        assert any("Failed to load run record for 'broken-session': DB query failed" in w for w in outcome.warnings)


class ResumeCliTests:
    """CLI integration tests for wt resume command."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem, catalog: CatalogHelper, runs: RunFactory) -> None:
        self.db = WorktreeDb(path=fs.base_path)
        self.catalog = catalog
        self.runs = runs

    def test_resume_cli_explicit_session_task(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify CLI 'wt resume <session_id>' resumes an explicit task run."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(self.catalog)
        self.runs.create_paused(session_id="task-explicit-1", blueprint=blueprint.catalog_item)

        result = runner.invoke(app, ["resume", "task-explicit-1"])
        assert result.exit_code == 0
        assert "task-explicit-1" in result.output

    def test_resume_cli_explicit_session_workflow(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify CLI 'wt resume <session_id>' resumes an explicit workflow run."""
        git_fs.init_repo()
        monkeypatch.chdir(git_fs.base_path)
        blueprint = _save_resume_blueprint(CatalogHelper(git_fs))
        git_db = WorktreeDb(path=git_fs.base_path)
        RunFactory(git_db.runs).create_paused(session_id="wf-explicit-1", blueprint=blueprint.catalog_item)

        result = runner.invoke(app, ["resume", "wf-explicit-1"])
        assert result.exit_code == 0
        assert "wf-explicit-1" in result.output

    def test_resume_cli_auto_resumes_latest_paused(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
    ) -> None:
        """Verify CLI 'wt resume' with no arguments auto-resumes the latest paused session."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(self.catalog)
        self.runs.create_paused(session_id="task-latest-1", blueprint=blueprint.catalog_item)
        self.runs.create_paused(session_id="task-latest-2", blueprint=blueprint.catalog_item)

        result = runner.invoke(app, ["resume"])
        assert result.exit_code == 0
        assert "task-latest-2" in result.output

    def test_resume_cli_not_paused_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt resume' fails when the target session is not in 'paused' status."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(self.catalog)
        self.runs.create(
            session_id="task-running",
            blueprint_name=blueprint.instance.name,
            blueprint_key=blueprint.catalog_item.key,
            status=RunStatus.RUNNING,
            completed_at=None,
        )

        result = runner.invoke(app, ["resume", "task-running"])
        assert result.exit_code == 1
        assert "Resume Failed" in result.output
        assert "Cannot resume session 'task-running': status is 'running' (expected paused)." in result.output

    def test_resume_cli_missing_sandbox_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt resume' fails when sandbox directory was deleted."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(self.catalog)
        checkpoint = make_checkpoint(sandbox_path="/tmp/nonexistent-sandbox-dir", use_sandbox=True)
        self.runs.create_paused(
            session_id="task-bad-box",
            blueprint=blueprint.catalog_item,
            checkpoint=checkpoint,
        )

        result = runner.invoke(app, ["resume", "task-bad-box"])
        assert result.exit_code == 1
        assert "Resume Failed" in result.output
        assert "no longer exists" in result.output

    def test_resume_cli_corrupt_checkpoint_exits_1(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt resume' fails cleanly on corrupt checkpoint JSON."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(self.catalog)
        self.runs.create(
            session_id="task-corrupt",
            blueprint_name=blueprint.instance.name,
            blueprint_key=blueprint.catalog_item.key,
            status=RunStatus.RUNNING,
            completed_at=None,
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
        blueprint = _save_resume_blueprint(
            self.catalog,
            steps=[
                {"id": "step-1", "run": "echo 1"},
                {"id": "step-2", "run": "exit 1", "on_failure": "prompt_user"},
            ],
        )
        self.runs.create_paused(session_id="task-pause-again", blueprint=blueprint.catalog_item)

        class _InterruptPrompter:
            is_interactive: bool = True

            def prompt_step_failure(self, **kwargs: object) -> FailurePromptDecision:
                raise KeyboardInterrupt

            def prompt_loop_max_iterations(self, **kwargs: object) -> LoopPromptDecision:
                raise KeyboardInterrupt

        monkeypatch.setattr(
            "worktree.cli.resume.commands.root.DispatcherFailurePrompter",
            lambda *args, **kwargs: _InterruptPrompter(),
        )

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = BlueprintResumeService(
            session_id="task-pause-again",
            path=ctx.cwd,
            db=ctx.db.runs,
            catalog_db=ctx.db.catalog,
            failure_prompter=_InterruptPrompter(),
        ).execute()
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
        blueprint = _save_resume_blueprint(
            self.catalog,
            steps=[
                {"id": "step-1", "run": "echo 1"},
                {"id": "step-2", "run": "exit 42"},
            ],
        )
        self.runs.create_paused(session_id="task-fail-run", blueprint=blueprint.catalog_item)

        result = runner.invoke(app, ["resume", "task-fail-run"])
        assert result.exit_code == 1

    def test_resume_cli_no_tty_aborts_prompt_user(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify non-interactive mode aborts failure prompts cleanly."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(
            self.catalog,
            steps=[
                {"id": "step-1", "run": "echo 1"},
                {"id": "step-2", "run": "exit 1", "on_failure": "prompt_user"},
            ],
        )
        self.runs.create_paused(session_id="task-non-int", blueprint=blueprint.catalog_item)

        result = runner.invoke(app, ["resume", "task-non-int", "--no-tty"])
        assert result.exit_code == 1
        assert "Resume Failed" in result.output

    def test_resume_cli_cancelled_status(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CLI 'wt resume' handles cancelled status cleanly."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(self.catalog)
        self.runs.create_paused(session_id="task-cancel", blueprint=blueprint.catalog_item)

        def cancel_resume(*_args: object, **_kwargs: object):
            record = self.db.runs.get("task-cancel")
            assert record is not None
            self.db.runs.update_status("task-cancel", RunStatus.CANCELLED, error_message="Cancelled by user.")
            return make_run_outcome(
                status=RunStatus.CANCELLED,
                errors=["Cancelled by user."],
                session_id="task-cancel",
                sandbox_path=Path(".worktree/sandboxes/sbx-run-1"),
            )

        monkeypatch.setattr(
            "worktree.core.engine.services.resume.Engine.resume",
            cancel_resume,
        )

        result = runner.invoke(app, ["resume", "task-cancel"])
        assert result.exit_code == 1
        assert "Cancelled by user." in result.output

    def test_resume_json_format_emits_ndjson_stream(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: _RetryPrompter,
    ) -> None:
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(self.catalog)
        self.runs.create_paused(session_id="resume_json_1", blueprint=blueprint.catalog_item)

        result = runner.invoke(app, ["resume", "resume_json_1", "--format", "json"])

        assert result.exit_code == 0
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        parsed_events = [json.loads(line) for line in lines]
        event_types = [e["event_type"] for e in parsed_events]
        assert "RunSuccessEvent" in event_types
        success_event = next(e for e in parsed_events if e["event_type"] == "RunSuccessEvent")
        assert success_event["payload"]["status"] == "completed"


class ResumeCommandDirectTests:
    """Unit tests for resume_command Typer-unaware handler."""

    def test_resume_command_resumes_paused_session(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
        mock_interactive_prompter: None,
        catalog: CatalogHelper,
        runs: RunFactory,
    ) -> None:
        """Verify resume_command resumes a paused session via context."""
        fs.create_config_file()
        monkeypatch.chdir(fs.base_path)
        blueprint = _save_resume_blueprint(catalog)
        runs.create_paused(session_id="direct-res-1", blueprint=blueprint.catalog_item)

        ctx = make_cli_context(cwd=fs.base_path)
        outcome = resume_command(ctx, session_id="direct-res-1")
        assert outcome.ok
        assert outcome.run_record is not None
        assert outcome.run_record.status == RunStatus.COMPLETED
