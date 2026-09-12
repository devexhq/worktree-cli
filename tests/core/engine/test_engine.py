"""Unit tests for the Engine.run facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.helpers import (
    CatalogHelper,
    FileSystem,
    GitFileSystem,
    make_cmd_step,
    make_run_outcome,
    make_step_result,
)
from worktree.core.blueprint import Blueprint, BlueprintDefinition
from worktree.core.catalog import Catalog
from worktree.core.db import RunsRepository, RunStatus, WorktreeDb
from worktree.core.engine import Engine, EngineInputError, RunRequest, load_session_run
from worktree.core.inputs import InputType, ParameterInput
from worktree.core.runtime import RunContext, RunOutcome
from worktree.core.step import LoopStepBlock, StepDefinition, StepType


def _task_blueprint(
    *,
    name: str = "lint",
    use_sandbox: bool = True,
    steps: list[StepDefinition] | None = None,
) -> Blueprint:
    return Blueprint(
        BlueprintDefinition(
            name=name,
            use_sandbox=use_sandbox,
            steps=list(steps) if steps is not None else [make_cmd_step()],
        )
    )


def _workflow_blueprint(*, name: str = "ship", loop: bool = False) -> Blueprint:
    steps: list[Any] = [make_cmd_step(step_id="ruff")]
    if loop:
        steps.append(
            LoopStepBlock.model_validate(
                {
                    "id": "retry",
                    "type": "loop",
                    "until": ["steps.unit.exit_code == 0"],
                    "do": [make_cmd_step(step_id="unit", command="echo hi").model_dump()],
                }
            )
        )
    return Blueprint(
        BlueprintDefinition(
            name=name,
            use_sandbox=False,
            steps=steps,
        )
    )


def _input_blueprint() -> Blueprint:
    return Blueprint(
        BlueprintDefinition(
            name="commit",
            use_sandbox=False,
            inputs={
                "message": ParameterInput(type=InputType.STRING, required=True, aliases=["-m"]),
                "allow_empty": ParameterInput(type=InputType.BOOLEAN, default=False),
            },
            steps=[make_cmd_step()],
        )
    )


class EngineConstructTests:
    """Unit tests for Engine initialization and contracts."""

    def test_construct_resolves_path(self, tmp_path: Path) -> None:
        db = RunsRepository(tmp_path)
        catalog = Catalog(tmp_path)
        engine = Engine(tmp_path, db=db, catalog=catalog)

        assert engine.path == tmp_path.resolve()


class EngineRunDelegationTests:
    """Unit tests for Engine.run execution, persistence, and error handling."""

    catalog: Catalog

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        fs.create_config_file()
        self.catalog = Catalog(path=fs.base_path, db=worktree_db.catalog)

    @pytest.mark.slow
    def test_run_unstubbed_executes_step_and_records_result(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        """Verify Engine.run executes a real step end to end without stubbing run_steps."""
        step = make_cmd_step(step_id="echo_step", command="echo delegation-ok")
        blueprint = _task_blueprint(steps=[step], use_sandbox=False)
        run_request = RunRequest(use_sandbox=False, session_id="task_unstubbed_step")
        outcome = Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(blueprint, run_request)
        session_json = load_session_run(fs.base_path, "task_unstubbed_step")

        normalized_outcome = outcome.model_copy(
            update={"step_results": [s.model_copy(update={"duration_seconds": 0.05}) for s in outcome.step_results]}
        )
        expected_step_result = make_step_result(step_id="echo_step", stdout="delegation-ok\n")
        expected_run_outcome = make_run_outcome(
            step_results=[expected_step_result], sandbox_path=fs.base_path, session_id="task_unstubbed_step"
        )

        # Assert run outcome
        assert normalized_outcome.ok is True
        assert normalized_outcome == expected_run_outcome

        # Assert DB run record
        record = worktree_db.runs.get(session_id="task_unstubbed_step")
        assert record is not None
        assert record.status == RunStatus.COMPLETED
        assert record.completed_at is not None

        # Assert session run JSON
        assert session_json is not None
        normalized_session_json = session_json.model_copy(
            update={"step_results": [s.model_copy(update={"duration_seconds": 0.05}) for s in outcome.step_results]}
        )
        assert normalized_session_json.status == RunStatus.COMPLETED.value
        assert normalized_session_json.step_results == expected_run_outcome.step_results

    def test_run_delegates_to_run_steps(
        self, monkeypatch: pytest.MonkeyPatch, fs: FileSystem, worktree_db: WorktreeDb
    ) -> None:
        steps = [make_cmd_step(step_id="one"), make_cmd_step(step_id="two")]
        blueprint = _task_blueprint(steps=steps, use_sandbox=True)
        observer = MagicMock()
        expected = RunOutcome(status=RunStatus.COMPLETED, step_results=[], sandbox_path=fs.base_path)
        captured: dict[str, RunContext] = {}

        def fake_run_steps(context: RunContext) -> RunOutcome:
            captured["context"] = context
            return expected

        monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

        outcome = Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(
            blueprint,
            RunRequest(
                use_sandbox=True,
                keep=True,
                agent="copilot",
                session_id="task_demo",
                observer=observer,
                inputs={"message": "hi"},
                no_tty=True,
                failure_prompter=None,
            ),
        )

        assert outcome == expected.model_copy(update={"session_id": "task_demo"})
        context = captured["context"]
        assert context.steps == steps
        assert context.cwd == fs.base_path.resolve()
        assert context.use_sandbox is True
        assert context.keep is True
        assert context.agent == "copilot"
        assert context.observer is observer
        assert context.inputs == {"message": "hi"}
        assert context.no_tty is True
        assert context.failure_prompter is None
        assert context.pause_store is not None
        assert context.resume_from is None

    @pytest.mark.parametrize(
        ("caller_use_sandbox", "definition_use_sandbox", "expected"),
        [
            pytest.param(None, True, True, id="caller_default_definition_true"),
            pytest.param(None, False, False, id="caller_default_definition_false"),
            pytest.param(True, True, True, id="caller_true_definition_true"),
            pytest.param(True, False, False, id="caller_true_definition_false_disables"),
            pytest.param(False, True, False, id="caller_false_overrides_definition_true"),
            pytest.param(False, False, False, id="caller_false_definition_false"),
        ],
    )
    def test_run_use_sandbox_logic(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fs: FileSystem,
        worktree_db: WorktreeDb,
        caller_use_sandbox: bool | None,
        definition_use_sandbox: bool,
        expected: bool,
    ) -> None:
        captured: dict[str, RunContext] = {}

        def fake_run_steps(context: RunContext) -> RunOutcome:
            captured["context"] = context
            return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

        monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

        Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(
            _task_blueprint(use_sandbox=definition_use_sandbox),
            RunRequest(use_sandbox=caller_use_sandbox, session_id="task_sandbox"),
        )

        assert captured["context"].use_sandbox is expected

    def test_run_persists_completed_task_row(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        outcome = Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(
            _task_blueprint(use_sandbox=False),
            RunRequest(use_sandbox=False, session_id="task_persist"),
        )

        assert outcome.ok
        record = worktree_db.runs.get("task_persist")
        assert record is not None
        assert record.blueprint_name == "lint"
        assert record.blueprint_key == "lint"
        assert record.status is RunStatus.COMPLETED
        assert record.completed_at is not None

    def test_run_persists_workflow_row_with_empty_branch(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        outcome = Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(
            _workflow_blueprint(),
            RunRequest(use_sandbox=False, session_id="workflow_persist"),
        )

        assert outcome.ok
        record = worktree_db.runs.get("workflow_persist")
        assert record is not None
        assert record.blueprint_name == "ship"
        assert record.blueprint_key == "ship"
        assert record.branch_name == ""
        assert record.status is RunStatus.COMPLETED

    def test_run_accepts_loop_steps_in_workflow(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        outcome = Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(
            _workflow_blueprint(loop=True), RunRequest(session_id="workflow_loop")
        )

        assert outcome.status is RunStatus.COMPLETED
        record = worktree_db.runs.get("workflow_loop")
        assert record is not None
        assert record.status is RunStatus.COMPLETED

    def test_insert_failure_warns_and_still_runs(
        self, monkeypatch: pytest.MonkeyPatch, fs: FileSystem, worktree_db: WorktreeDb
    ) -> None:
        captured: dict[str, RunContext] = {}

        def fake_run_steps(context: RunContext) -> RunOutcome:
            captured["context"] = context
            return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("disk full")

        monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)
        monkeypatch.setattr("worktree.core.db.repositories.runs.RunsRepository.create", boom)

        outcome = Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(
            _task_blueprint(), RunRequest(session_id="task_insert_fail")
        )

        assert captured["context"].pause_store is None
        assert any(warning.startswith("Failed to record run start in database:") for warning in outcome.warnings)
        assert worktree_db.runs.get("task_insert_fail") is None

    def test_update_failure_warns_and_returns_outcome(
        self, monkeypatch: pytest.MonkeyPatch, fs: FileSystem, worktree_db: WorktreeDb
    ) -> None:
        expected = RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path, warnings=["step note"])

        monkeypatch.setattr(
            "worktree.core.engine.engine.run_steps",
            lambda _context: expected,
        )
        monkeypatch.setattr(
            "worktree.core.db.repositories.runs.RunsRepository.update_status",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("locked")),
        )

        outcome = Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(
            _task_blueprint(), RunRequest(session_id="task_update_fail")
        )

        assert outcome is not expected
        assert outcome.warnings[0] == "step note"
        assert any(warning.startswith("Failed to update run status in database:") for warning in outcome.warnings)
        record = worktree_db.runs.get("task_update_fail")
        assert record is not None
        assert record.status is RunStatus.RUNNING

    def test_omitted_session_id_uses_blueprint_prefix(
        self, monkeypatch: pytest.MonkeyPatch, fs: FileSystem, worktree_db: WorktreeDb
    ) -> None:
        monkeypatch.setattr(
            "worktree.core.engine.engine.run_steps",
            lambda _context: RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path),
        )

        outcome = Engine(fs.base_path, db=worktree_db.runs, catalog=self.catalog).run(
            _task_blueprint(use_sandbox=False), RunRequest(use_sandbox=False)
        )

        records = worktree_db.runs.list()
        assert len(records) == 1
        assert records[0].session_id.startswith("blueprint_")
        assert len(records[0].session_id) == len("blueprint_") + 8
        assert outcome.session_id == records[0].session_id


class EngineRunInputsTests:
    """Unit tests for Engine.run parameter inputs resolution and validation."""

    db: WorktreeDb
    catalog: Catalog

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        fs.create_config_file()
        self.db = WorktreeDb(path=fs.base_path)
        self.catalog = Catalog(path=fs.base_path, db=self.db.catalog)

    def test_run_without_request_uses_defaults(self, monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
        captured: dict[str, RunContext] = {}

        def fake_run_steps(context: RunContext) -> RunOutcome:
            captured["context"] = context
            return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

        monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

        outcome = Engine(fs.base_path, db=self.db.runs, catalog=self.catalog).run(_task_blueprint(use_sandbox=False))

        assert captured["context"].inputs == {}
        assert outcome.session_id is not None
        assert outcome.session_id.startswith("blueprint_")

    def test_run_applies_input_defaults(self, monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
        captured: dict[str, RunContext] = {}

        def fake_run_steps(context: RunContext) -> RunOutcome:
            captured["context"] = context
            return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

        monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

        Engine(fs.base_path, db=self.db.runs, catalog=self.catalog).run(
            _input_blueprint(), RunRequest(inputs={"message": "ship it"})
        )

        assert captured["context"].inputs == {"message": "ship it", "allow_empty": False}

    def test_run_parses_cli_args(self, monkeypatch: pytest.MonkeyPatch, fs: FileSystem) -> None:
        captured: dict[str, RunContext] = {}

        def fake_run_steps(context: RunContext) -> RunOutcome:
            captured["context"] = context
            return RunOutcome(status=RunStatus.COMPLETED, sandbox_path=fs.base_path)

        monkeypatch.setattr("worktree.core.engine.engine.run_steps", fake_run_steps)

        Engine(fs.base_path, db=self.db.runs, catalog=self.catalog).run(
            _input_blueprint(), RunRequest(cli_args=["-m", "from argv"])
        )

        assert captured["context"].inputs == {"message": "from argv", "allow_empty": False}

    def test_run_missing_required_input_raises_before_insert(self, fs: FileSystem) -> None:
        with pytest.raises(EngineInputError, match="Missing required input 'message'") as exc_info:
            Engine(fs.base_path, db=self.db.runs, catalog=self.catalog).run(_input_blueprint())

        assert exc_info.value.result.missing == ["message"]
        assert self.db.runs.list() == []

    def test_run_invalid_input_raises_before_insert(self, fs: FileSystem) -> None:
        with pytest.raises(EngineInputError, match="expects an integer") as exc_info:
            Engine(fs.base_path, db=self.db.runs, catalog=self.catalog).run(
                Blueprint(
                    BlueprintDefinition(
                        name="count",
                        use_sandbox=False,
                        inputs={"n": ParameterInput(type=InputType.INTEGER, required=True)},
                        steps=[make_cmd_step()],
                    )
                ),
                RunRequest(cli_args=["-i", "n=nope"]),
            )

        assert exc_info.value.result.errors
        assert self.db.runs.list() == []


class EngineExecutionMetadataTests:
    """Tests verifying WT_BLUEPRINT_* env variables populated by Engine."""

    def test_engine_run_populates_blueprint_metadata(self, fs: FileSystem) -> None:
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


class EngineSessionPersistenceTests:
    """Integration tests verifying Engine persists run.json for runs and resumes."""

    def test_engine_run_persists_run_json(self, git_fs: GitFileSystem) -> None:
        """Verify Engine.run writes run.json with step results."""
        git_fs.init_repo()
        helper = CatalogHelper(git_fs)
        helper.save(
            helper.blueprint(
                key="test-task",
                name="test-task",
                summary="Test task persistence",
                steps=[
                    {
                        "id": "step-1",
                        "name": "Echo step",
                        "run": "echo 'session step complete'",
                    }
                ],
            )
        )
        db = WorktreeDb(git_fs.base_path)
        catalog = Catalog(git_fs.base_path, db=db.catalog)
        engine = Engine(git_fs.base_path, db=db.runs, catalog=catalog)

        blueprint = Blueprint.load("test-task", catalog=catalog)

        request = RunRequest(session_id="task_persisted_1", use_sandbox=True)
        outcome = engine.run(blueprint, request)

        assert outcome.status == RunStatus.COMPLETED

        payload = load_session_run(git_fs.base_path, "task_persisted_1")
        assert payload is not None
        assert payload.session_id == "task_persisted_1"
        assert payload.name == "test-task"
        assert payload.status == "completed"
        assert len(payload.step_results) == 1
        assert "session step complete" in payload.step_results[0].stdout
