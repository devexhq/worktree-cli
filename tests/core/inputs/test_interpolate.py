"""Unit tests for template interpolation with inputs and execution metadata."""

from __future__ import annotations

from worktree.core.inputs import interpolate_step_fields, interpolate_string
from worktree.core.step import (
    ExecutionIdentity,
    ExecutionMetadata,
    PreviousStepMetadata,
    StepDefinition,
    StepMetadata,
    StepType,
    TaskMetadata,
    WorkflowMetadata,
    build_execution_metadata,
)


class InputInterpolateTests:
    """Unit tests for template interpolation in strings and step definitions."""

    def test_interpolate_string_replaces_placeholders(self) -> None:
        rendered = interpolate_string(
            "git commit -m '${{ inputs.message }}' flag=${{ inputs.allow_empty }}",
            {"message": "ship it", "allow_empty": False},
        )
        assert rendered == "git commit -m 'ship it' flag=False"

    def test_interpolate_string_without_dollar_replaces_inputs(self) -> None:
        rendered = interpolate_string(
            "echo {{ inputs.target }}",
            {"target": "src/"},
        )
        assert rendered == "echo src/"

    def test_interpolate_string_keeps_unknown_placeholders(self) -> None:
        template = "echo ${{ inputs.missing }} {{ unknown.path }}"
        assert interpolate_string(template, {"other": "x"}) == template

    def test_interpolate_string_with_execution_metadata(self) -> None:
        metadata = ExecutionMetadata(
            step=StepMetadata(id="step-build", name="Build Step", index=2, attempt=1),
            task=TaskMetadata(name="my-task", sha="sess_123"),
            workflow=WorkflowMetadata(name="ci-flow", sha="flow_456"),
            previous_step=PreviousStepMetadata(
                id="step-init",
                name="Init Step",
                index="1",
                status="completed",
                exit_code="0",
            ),
        )

        template = (
            "id={{ step.id }} name={{ step.name }} idx={{ step.index }} attempt={{ step.attempt }} "
            "task={{ task.name }}:{{ task.sha }} flow={{ workflow.name }}:{{ workflow.sha }} "
            "prev={{ previous_step.id }}:{{ previous_step.status }}:{{ previous_step.exit_code }}"
        )
        rendered = interpolate_string(template, metadata=metadata)
        assert rendered == (
            "id=step-build name=Build Step idx=2 attempt=1 "
            "task=my-task:sess_123 flow=ci-flow:flow_456 "
            "prev=step-init:completed:0"
        )

    def test_interpolate_string_with_dollar_metadata(self) -> None:
        metadata = ExecutionMetadata(
            step=StepMetadata(id="step-1", index=1, attempt=2),
        )
        rendered = interpolate_string("echo '${{ step.id }}' attempt=${{ step.attempt }}", metadata=metadata)
        assert rendered == "echo 'step-1' attempt=2"

    def test_interpolate_string_empty_metadata_fields_resolve_to_empty(self) -> None:
        metadata = build_execution_metadata(StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi"))
        template = "t={{ task.name }} flow={{ workflow.name }} prev_status={{ previous_step.status }}"
        rendered = interpolate_string(template, metadata=metadata)
        assert rendered == "t= flow= prev_status="

    def test_interpolate_step_fields_updates_command_and_env(self) -> None:
        step = StepDefinition(
            id="s1",
            type=StepType.COMMAND,
            command="echo ${{ inputs.message }}",
            env={"MSG": "${{ inputs.message }}", "STATIC": "keep"},
        )

        updated = interpolate_step_fields(step, {"message": "hello"})
        assert updated.command == "echo hello"
        assert updated.env == {"MSG": "hello", "STATIC": "keep"}

    def test_interpolate_step_fields_updates_with_metadata(self) -> None:
        step = StepDefinition(
            id="s1",
            name="Compile",
            type=StepType.COMMAND,
            command="echo {{ step.id }}:{{ step.attempt }} prev={{ previous_step.status }} input={{ inputs.msg }}",
            env={"STEP_ATTEMPT": "{{ step.attempt }}", "PREV_ID": "{{ previous_step.id }}"},
        )
        metadata = build_execution_metadata(
            step,
            step_index=2,
            attempt=3,
            identity=ExecutionIdentity(task_name="task-1", task_sha="sha123"),
            previous_step=PreviousStepMetadata(id="s0", status="completed", exit_code="0", index="1"),
        )
        updated = interpolate_step_fields(step, inputs={"msg": "run"}, metadata=metadata)
        assert updated.command == "echo s1:3 prev=completed input=run"
        assert updated.env == {"STEP_ATTEMPT": "3", "PREV_ID": "s0"}

    def test_interpolate_step_fields_updates_prompt_and_script_path(self) -> None:
        prompt_step = StepDefinition(
            id="agent",
            type=StepType.AGENT,
            prompt="do ${{ inputs.message }} in step {{ step.id }}",
        )
        script_step = StepDefinition(
            id="script",
            type=StepType.SCRIPT,
            script_path="scripts/${{ inputs.message }}_{{ step.attempt }}.sh",
        )
        metadata = build_execution_metadata(prompt_step, step_index=1, attempt=2)

        assert (
            interpolate_step_fields(prompt_step, {"message": "hello"}, metadata=metadata).prompt
            == "do hello in step agent"
        )
        assert (
            interpolate_step_fields(script_step, {"message": "hello"}, metadata=metadata).script_path
            == "scripts/hello_2.sh"
        )

    def test_interpolate_string_with_historical_steps(self) -> None:
        s0 = PreviousStepMetadata(id="step-init", name="Init Step", index="1", status="completed", exit_code="0")
        s1 = PreviousStepMetadata(id="step-build", name="Build Step", index="2", status="failed", exit_code="2")
        metadata = ExecutionMetadata(
            step=StepMetadata(id="step-deploy", name="Deploy Step", index=3, attempt=1),
            previous_step=s1,
            steps=[s0, s1],
        )

        template = (
            "first_id={{ steps[0].id }} first_idx={{ steps[0].index }} first_status={{ steps[0].status }} "
            "last_id={{ steps[-1].id }} last_idx={{ steps[-1].index }} last_status={{ steps[-1].status }} "
            "prev_status={{ previous_step.status }} "
            "by_id_build_code={{ steps.step-build.exit_code }} "
            "by_bracket_id={{ steps['step-init'].status }} "
            "by_unquoted_id={{ steps[step-build].status }}"
        )
        rendered = interpolate_string(template, metadata=metadata)
        assert rendered == (
            "first_id=step-init first_idx=1 first_status=completed "
            "last_id=step-build last_idx=2 last_status=failed "
            "prev_status=failed "
            "by_id_build_code=2 "
            "by_bracket_id=completed "
            "by_unquoted_id=failed"
        )

    def test_interpolate_historical_steps_out_of_range_and_missing_yields_empty(self) -> None:
        s0 = PreviousStepMetadata(id="step-init", name="Init Step", index="1", status="completed", exit_code="0")
        metadata = ExecutionMetadata(
            step=StepMetadata(id="step-test", index=2, attempt=1),
            previous_step=s0,
            steps=[s0],
        )

        template = "out={{ steps[5].status }} neg_out={{ steps[-5].id }} missing_id={{ steps.unknown.exit_code }}"
        rendered = interpolate_string(template, metadata=metadata)
        assert rendered == "out= neg_out= missing_id="

    def test_interpolate_empty_historical_steps_yields_empty(self) -> None:
        metadata = ExecutionMetadata(
            step=StepMetadata(id="step-init", index=1, attempt=1),
            previous_step=PreviousStepMetadata(),
            steps=[],
        )

        template = "first={{ steps[0].id }} last={{ steps[-1].status }} named={{ steps.build.exit_code }}"
        rendered = interpolate_string(template, metadata=metadata)
        assert rendered == "first= last= named="

    def test_interpolate_step_fields_noop_without_inputs_or_metadata(self) -> None:
        step = StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi")
        assert interpolate_step_fields(step) is step
        assert interpolate_step_fields(step, {}) is step
