"""Integration tests verifying blueprint metadata injection via Engine."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.blueprint import Blueprint, BlueprintDefinition
from worktree.core.catalog import Catalog
from worktree.core.db import RunsRepository
from worktree.core.engine import Engine, RunRequest
from worktree.core.step import StepDefinition, StepType


class EngineExecutionMetadataTests:
    """Tests verifying WT_BLUEPRINT_* env variables populated by Engine."""

    def test_engine_run_task_populates_blueprint_metadata(self, fs: FileSystem) -> None:
        fs.create_config_file()
        step = StepDefinition(
            id="task_step",
            type=StepType.COMMAND,
            command='echo "BLUEPRINT=$WT_BLUEPRINT_NAME KEY=$WT_BLUEPRINT_SHA"',
        )
        blueprint = Blueprint(
            BlueprintDefinition(
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
        assert "BLUEPRINT=my-test-task" in output
        assert "KEY=my-test-task" in output

    def test_engine_run_workflow_populates_blueprint_metadata(self, fs: FileSystem) -> None:
        fs.create_config_file()
        step = StepDefinition(
            id="flow_step",
            type=StepType.COMMAND,
            command='echo "BLUEPRINT=$WT_BLUEPRINT_NAME KEY=$WT_BLUEPRINT_SHA"',
        )
        blueprint = Blueprint(
            BlueprintDefinition(
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
        assert "BLUEPRINT=my-test-workflow" in output
        assert "KEY=my-test-workflow" in output
