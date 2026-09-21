"""Contract tests for ResumableRun: classification, blueprint resolution, and handle contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.builders import BlueprintBuilder, StepBuilder, WorkspaceBuilder
from worktree.core.blueprint import Blueprint
from worktree.core.catalog import Catalog
from worktree.core.db import RunsRepository, RunStatus
from worktree.core.engine import EngineResumeError, EngineResumeStatus, ResumableRun
from worktree.core.runtime import RunCheckpoint
from worktree.core.step.models import LoopStepBlock, StepDefinition


def _checkpoint(
    *,
    pending_step_id: str = "publish",
    use_sandbox: bool = False,
    sandbox_path: str | None = None,
) -> RunCheckpoint:
    return RunCheckpoint(
        next_step_index=1,
        pending_step_id=pending_step_id,
        diagnostic="Step 'publish' failed: boom",
        use_sandbox=use_sandbox,
        sandbox_path=sandbox_path,
    )


def _task_blueprint(*, name: str = "lint", loop: bool = False) -> tuple[Blueprint, list[StepDefinition]]:
    """Build a 3-step (setup/publish/later) task blueprint, optionally with a trailing loop block.

    Returns the blueprint alongside its flattened step list (loop sub-steps expanded, matching
    ResumableRun's own _collect_blueprint_steps), so callers can assert whole-object equality
    against handle.steps instead of re-deriving the expected steps by hand.
    """
    setup = StepBuilder.command("echo setup").with_id("setup").build()
    publish = StepBuilder.command("exit 1").with_id("publish").build()
    later = StepBuilder.command("echo later").with_id("later").build()
    builder = BlueprintBuilder(name).with_use_sandbox(False).with_step(setup).with_step(publish).with_step(later)
    steps = [setup, publish, later]
    if loop:
        unit = StepBuilder.command("echo hi").with_id("unit").build()
        builder.with_step(LoopStepBlock(id="retry", type="loop", until=["steps.unit.exit_code == 0"], do=[unit]))
        steps = [setup, publish, later, unit]
    return Blueprint(builder.build()), steps


def _seed_paused_run(db: RunsRepository, session_id: str, checkpoint: RunCheckpoint, *, name: str = "lint") -> None:
    db.create(session_id, blueprint_name=name, blueprint_key=name, status=RunStatus.RUNNING)
    db.save_pause(session_id, checkpoint.model_dump_json(), checkpoint.diagnostic)


class ResumableRunHandleTests:
    """Contract tests for ResumableRun.load's happy-path and not-found handle shape."""

    def test_resumable_run_load_is_resumable_with_explicit_blueprint(self, tmp_path: Path) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        runs_repo = RunsRepository(workspace)
        blueprint, expected_steps = _task_blueprint()
        checkpoint = _checkpoint()
        _seed_paused_run(runs_repo, "task-1", checkpoint)

        handle = ResumableRun.load("task-1", blueprint, path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.is_resumable is True
        assert handle.status == EngineResumeStatus.OK
        assert handle.checkpoint == checkpoint
        assert handle.steps == expected_steps

    def test_resumable_run_load_not_found_when_session_missing(self, tmp_path: Path) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        runs_repo = RunsRepository(workspace)

        handle = ResumableRun.load("missing", path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.is_resumable is False
        assert handle.status == EngineResumeStatus.NOT_FOUND
        assert str(handle) == "Session 'missing' not found."
        with pytest.raises(EngineResumeError) as exc_info:
            handle.ready()
        assert exc_info.value.status == EngineResumeStatus.NOT_FOUND


class ResumableRunBlueprintResolutionTests:
    """Contract tests for ResumableRun.load's blueprint auto-load and step-validity checks."""

    def test_resumable_run_load_omitted_blueprint_auto_loads_from_catalog_by_stored_blueprint_key(
        self, tmp_path: Path
    ) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        blueprints_dir = workspace / ".worktree" / "catalog" / "blueprints"
        blueprints_dir.mkdir(parents=True, exist_ok=True)
        raw_yaml = (
            "steps:\n"
            "  - id: setup\n    run: echo setup\n"
            "  - id: publish\n    run: echo publish\n"
            "  - id: later\n    run: echo later\n"
        )
        (blueprints_dir / "lint.yml").write_text(raw_yaml, encoding="utf-8")
        runs_repo = RunsRepository(workspace)
        _seed_paused_run(runs_repo, "task-2", _checkpoint(), name="lint")

        handle = ResumableRun.load("task-2", path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.is_resumable is True
        assert handle.blueprint is not None
        assert handle.blueprint.definition.name == "lint"
        assert [s.id for s in handle.blueprint.definition.steps] == ["setup", "publish", "later"]

    def test_resumable_run_load_omitted_blueprint_missing_from_catalog_is_classified_failed(
        self, tmp_path: Path
    ) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        runs_repo = RunsRepository(workspace)
        _seed_paused_run(runs_repo, "task-3", _checkpoint(), name="missing-task")

        handle = ResumableRun.load("task-3", path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.is_resumable is False
        assert handle.status == EngineResumeStatus.FAILED
        assert "blueprint 'missing-task' not found" in str(handle)

    def test_resumable_run_load_pending_step_removed_from_blueprint_is_classified_corrupt_checkpoint(
        self, tmp_path: Path
    ) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        runs_repo = RunsRepository(workspace)
        blueprint, _ = _task_blueprint()
        checkpoint = _checkpoint(pending_step_id="removed-step")
        _seed_paused_run(runs_repo, "task-4", checkpoint)

        handle = ResumableRun.load("task-4", blueprint, path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.is_resumable is False
        assert handle.status == EngineResumeStatus.CORRUPT_CHECKPOINT
        assert "checkpoint is missing or corrupt" in str(handle)

    def test_resumable_run_load_accepts_loop_steps_in_workflow_blueprint(self, tmp_path: Path) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        runs_repo = RunsRepository(workspace)
        blueprint, expected_steps = _task_blueprint(loop=True)
        checkpoint = _checkpoint(pending_step_id="unit")
        _seed_paused_run(runs_repo, "task-5", checkpoint)

        handle = ResumableRun.load("task-5", blueprint, path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.is_resumable is True
        assert handle.steps == expected_steps


class ResumableRunClassificationTests:
    """Contract tests for every remaining non-OK EngineResumeStatus classification branch."""

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(RunStatus.COMPLETED, id="status_completed"),
            pytest.param(RunStatus.FAILED, id="status_failed"),
            pytest.param(RunStatus.RUNNING, id="status_running"),
            pytest.param(RunStatus.CANCELLED, id="status_cancelled"),
        ],
    )
    def test_resumable_run_load_non_paused_row_is_classified_wrong_status(
        self, tmp_path: Path, status: RunStatus
    ) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        runs_repo = RunsRepository(workspace)
        runs_repo.create("task_wrong", blueprint_name="lint", blueprint_key="lint", status=status)

        handle = ResumableRun.load("task_wrong", path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.status == EngineResumeStatus.WRONG_STATUS
        assert str(handle) == f"Cannot resume session 'task_wrong': status is '{status.value}' (expected paused)."

    def test_resumable_run_load_corrupt_checkpoint_json_is_classified_corrupt_checkpoint(self, tmp_path: Path) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        runs_repo = RunsRepository(workspace)
        runs_repo.create("task-6", blueprint_name="lint", blueprint_key="lint", status=RunStatus.RUNNING)
        runs_repo.save_pause("task-6", "not valid json", "boom")

        handle = ResumableRun.load("task-6", path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.is_resumable is False
        assert handle.status == EngineResumeStatus.CORRUPT_CHECKPOINT

    def test_resumable_run_load_missing_sandbox_path_is_classified_missing_sandbox(self, tmp_path: Path) -> None:
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_database().build()
        runs_repo = RunsRepository(workspace)
        checkpoint = _checkpoint(use_sandbox=True, sandbox_path=str(tmp_path / "gone"))
        _seed_paused_run(runs_repo, "task-7", checkpoint)

        handle = ResumableRun.load("task-7", path=workspace, db=runs_repo, catalog=Catalog(workspace))

        assert handle.is_resumable is False
        assert handle.status == EngineResumeStatus.MISSING_SANDBOX
