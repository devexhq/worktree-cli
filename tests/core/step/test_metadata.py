"""Unit tests for step execution metadata models, builders, and environment variables."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from worktree.core.step import (
    ExecutionIdentity,
    PreviousStepMetadata,
    StepDefinition,
    StepMetadata,
    StepResult,
    StepType,
    TaskMetadata,
    WorkflowMetadata,
    build_execution_metadata,
    metadata_to_env,
    previous_step_metadata_from_result,
)


class StepExecutionMetadataTests:
    """Unit tests for metadata builder and WT_* env dictionary formatting."""

    def test_build_execution_metadata_defaults(self) -> None:
        step = StepDefinition(id="step-build", type=StepType.COMMAND, command="echo test")
        metadata = build_execution_metadata(step)

        assert metadata.step.id == "step-build"
        assert metadata.step.name == ""
        assert metadata.step.index == 1
        assert metadata.step.attempt == 1
        assert metadata.task.name == ""
        assert metadata.task.sha == ""
        assert metadata.workflow.name == ""
        assert metadata.workflow.sha == ""
        assert metadata.previous_step.id == ""
        assert metadata.previous_step.name == ""
        assert metadata.previous_step.index == ""
        assert metadata.previous_step.status == ""
        assert metadata.previous_step.exit_code == ""

    def test_build_execution_metadata_with_identity_and_previous(self) -> None:
        step = StepDefinition(id="step-deploy", name="Deploy Artifact", type=StepType.COMMAND, command="echo deploy")
        identity = ExecutionIdentity(
            task_name="release-task",
            task_sha="task_run_123",
            workflow_name="release-flow",
            workflow_sha="flow_run_456",
        )
        previous = PreviousStepMetadata(
            id="step-build",
            name="Build Artifact",
            index="1",
            status="completed",
            exit_code="0",
        )

        metadata = build_execution_metadata(
            step,
            step_index=2,
            attempt=3,
            identity=identity,
            previous_step=previous,
        )

        assert metadata.step.id == "step-deploy"
        assert metadata.step.name == "Deploy Artifact"
        assert metadata.step.index == 2
        assert metadata.step.attempt == 3
        assert metadata.task.name == "release-task"
        assert metadata.task.sha == "task_run_123"
        assert metadata.workflow.name == "release-flow"
        assert metadata.workflow.sha == "flow_run_456"
        assert metadata.previous_step.id == "step-build"
        assert metadata.previous_step.name == "Build Artifact"
        assert metadata.previous_step.index == "1"
        assert metadata.previous_step.status == "completed"
        assert metadata.previous_step.exit_code == "0"

    def test_metadata_to_env_all_fifteen_keys_present_with_defaults(self) -> None:
        step = StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi")
        metadata = build_execution_metadata(step)
        env_map = metadata_to_env(metadata)

        expected_keys = {
            "WT_STEP_ID",
            "WT_STEP_NAME",
            "WT_STEP_INDEX",
            "WT_STEP_ATTEMPT",
            "WT_ITERATION_INDEX",
            "WT_TASK_NAME",
            "WT_TASK_SHA",
            "WT_WORKFLOW_NAME",
            "WT_WORKFLOW_SHA",
            "WT_PREVIOUS_STEP_ID",
            "WT_PREVIOUS_STEP_NAME",
            "WT_PREVIOUS_STEP_INDEX",
            "WT_PREVIOUS_STEP_STATUS",
            "WT_PREVIOUS_STEP_EXIT_CODE",
            "WT_STEPS_JSON",
        }
        assert set(env_map.keys()) == expected_keys
        assert env_map["WT_STEP_ID"] == "s1"
        assert env_map["WT_STEP_NAME"] == ""
        assert env_map["WT_STEP_INDEX"] == "1"
        assert env_map["WT_STEP_ATTEMPT"] == "1"
        assert env_map["WT_ITERATION_INDEX"] == "1"
        assert env_map["WT_TASK_NAME"] == ""
        assert env_map["WT_TASK_SHA"] == ""
        assert env_map["WT_WORKFLOW_NAME"] == ""
        assert env_map["WT_WORKFLOW_SHA"] == ""
        assert env_map["WT_PREVIOUS_STEP_ID"] == ""
        assert env_map["WT_PREVIOUS_STEP_NAME"] == ""
        assert env_map["WT_PREVIOUS_STEP_INDEX"] == ""
        assert env_map["WT_PREVIOUS_STEP_STATUS"] == ""
        assert env_map["WT_PREVIOUS_STEP_EXIT_CODE"] == ""
        assert env_map["WT_STEPS_JSON"] == "[]"

    def test_metadata_to_env_populated_values(self) -> None:
        step = StepDefinition(id="s2", name="Second Step", type=StepType.COMMAND, command="echo hi")
        step1_meta = PreviousStepMetadata(
            id="s1",
            name="First Step",
            index="1",
            status="ignored",
            exit_code="1",
        )
        metadata = build_execution_metadata(
            step,
            step_index=2,
            attempt=4,
            identity=ExecutionIdentity(task_name="t1", task_sha="sha1"),
            previous_step=step1_meta,
            steps=[step1_meta],
        )
        env_map = metadata_to_env(metadata)

        assert env_map["WT_STEP_ID"] == "s2"
        assert env_map["WT_STEP_NAME"] == "Second Step"
        assert env_map["WT_STEP_INDEX"] == "2"
        assert env_map["WT_STEP_ATTEMPT"] == "4"
        assert env_map["WT_TASK_NAME"] == "t1"
        assert env_map["WT_TASK_SHA"] == "sha1"
        assert env_map["WT_WORKFLOW_NAME"] == ""
        assert env_map["WT_WORKFLOW_SHA"] == ""
        assert env_map["WT_PREVIOUS_STEP_ID"] == "s1"
        assert env_map["WT_PREVIOUS_STEP_NAME"] == "First Step"
        assert env_map["WT_PREVIOUS_STEP_INDEX"] == "1"
        assert env_map["WT_PREVIOUS_STEP_STATUS"] == "ignored"
        assert env_map["WT_PREVIOUS_STEP_EXIT_CODE"] == "1"
        assert (
            env_map["WT_STEPS_JSON"]
            == '[{"id": "s1", "name": "First Step", "index": "1", "status": "ignored", "exit_code": "1"}]'
        )

    def test_build_execution_metadata_with_steps_defaults_previous_step(self) -> None:
        step = StepDefinition(id="s3", type=StepType.COMMAND, command="echo test")
        s1 = PreviousStepMetadata(id="s1", name="Init", index="1", status="completed", exit_code="0")
        s2 = PreviousStepMetadata(id="s2", name="Build", index="2", status="failed", exit_code="2")

        metadata = build_execution_metadata(step, step_index=3, steps=[s1, s2])

        assert len(metadata.steps) == 2
        assert metadata.steps[0] == s1
        assert metadata.steps[1] == s2
        assert metadata.previous_step == s2

    def test_previous_step_metadata_from_result(self) -> None:
        result = StepResult(
            step_id="step-test",
            status="completed",
            exit_code=0,
            stdout="all tests passed",
            stderr="",
            duration_seconds=1.2,
            attempts=1,
        )
        prev = previous_step_metadata_from_result(result, step_index=1, step_name="Run Tests")

        assert prev.id == "step-test"
        assert prev.name == "Run Tests"
        assert prev.index == "1"
        assert prev.status == "completed"
        assert prev.exit_code == "0"

    def test_models_forbid_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            StepMetadata(id="s1", index=1, attempt=1, extra_field="bad")  # pyright: ignore[reportCallIssue]
        with pytest.raises(ValidationError):
            TaskMetadata(name="t", extra_field="bad")  # pyright: ignore[reportCallIssue]
        with pytest.raises(ValidationError):
            WorkflowMetadata(name="w", extra_field="bad")  # pyright: ignore[reportCallIssue]
        with pytest.raises(ValidationError):
            PreviousStepMetadata(id="p", extra_field="bad")  # pyright: ignore[reportCallIssue]
        with pytest.raises(ValidationError):
            ExecutionIdentity(task_name="t", extra_field="bad")  # pyright: ignore[reportCallIssue]
