"""Integration tests verifying task and workflow metadata injection via Engine."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.blueprint import Blueprint, BlueprintDefinition, BlueprintKind
from worktree.core.catalog import Catalog
from worktree.core.db import RunsRepository
from worktree.core.engine import Engine, RunRequest
from worktree.core.step import StepDefinition, StepType


class EngineExecutionMetadataTests:
    """Tests verifying WT_TASK_* and WT_WORKFLOW_* env variables populated by Engine."""

    def test_engine_run_task_populates_task_metadata(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="task_step",
            type=StepType.COMMAND,
            command='echo "TASK=$WT_TASK_NAME SHA=$WT_TASK_SHA FLOW=$WT_WORKFLOW_NAME"',
        )
        blueprint = Blueprint(
            BlueprintDefinition(
                kind=BlueprintKind.TASK,
                name="my-test-task",
                use_sandbox=False,
                steps=[step],
            )
        )

        db = RunsRepository(fs.base_path)
        catalog = Catalog(fs.base_path)
        engine = Engine(fs.base_path, db=db, catalog=catalog)
        outcome = engine.run(blueprint, RunRequest(session_id="custom_sess_123", use_sandbox=False))

        assert outcome.ok is True
        assert len(outcome.step_results) == 1
        output = outcome.step_results[0].stdout
        assert "TASK=my-test-task" in output
        assert "SHA=custom_sess_123" in output
        assert "FLOW=" in output

    def test_engine_run_workflow_populates_workflow_metadata(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="flow_step",
            type=StepType.COMMAND,
            command='echo "TASK=$WT_TASK_NAME FLOW=$WT_WORKFLOW_NAME SHA=$WT_WORKFLOW_SHA"',
        )
        blueprint = Blueprint(
            BlueprintDefinition(
                kind=BlueprintKind.WORKFLOW,
                name="my-test-workflow",
                use_sandbox=False,
                steps=[step],
            )
        )

        db = RunsRepository(fs.base_path)
        catalog = Catalog(fs.base_path)
        engine = Engine(fs.base_path, db=db, catalog=catalog)
        outcome = engine.run(blueprint, RunRequest(session_id="flow_sess_456", use_sandbox=False))

        assert outcome.ok is True
        assert len(outcome.step_results) == 1
        output = outcome.step_results[0].stdout
        assert "TASK=" in output
        assert "FLOW=my-test-workflow" in output
        assert "SHA=flow_sess_456" in output
