"""Integration tests for StepExecution metadata injection and real process environment."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.step import (
    ExecutionIdentity,
    FailurePolicy,
    FailureSpec,
    PreviousStepMetadata,
    StepDefinition,
    StepExecution,
    StepType,
)


class StepExecutionMetadataIntegrationTests:
    """Tests verifying metadata availability, attempt counting, and retry orchestration with real processes."""

    def test_command_receives_wt_environment_variables(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="test_env_vars",
            name="Test Environment Variables",
            type=StepType.COMMAND,
            command='echo "ID=$WT_STEP_ID IDX=$WT_STEP_INDEX ATTEMPT=$WT_STEP_ATTEMPT PREV=$WT_PREVIOUS_STEP_ID"',
        )
        previous = PreviousStepMetadata(
            id="prev_step",
            name="Previous Step",
            index="1",
            status="completed",
            exit_code="0",
        )
        identity = ExecutionIdentity(task_name="my_task", task_sha="sha_999")

        result = StepExecution(
            step,
            sandbox_path=fs.base_path,
            step_index=2,
            identity=identity,
            previous_step=previous,
        ).run()

        assert result.ok is True
        assert "ID=test_env_vars IDX=2 ATTEMPT=1 PREV=prev_step" in result.stdout

    def test_command_drives_retry_success_via_wt_step_attempt(self, fs: FileSystem) -> None:
        """Verify real retry orchestration: fails on attempt 1, succeeds on attempt 2 without mocks."""
        step = StepDefinition(
            id="retry_command",
            type=StepType.COMMAND,
            command='if [ "$WT_STEP_ATTEMPT" -eq 1 ]; then echo "attempt 1 failed" >&2; exit 1; else echo "attempt 2 succeeded"; exit 0; fi',
            on_failure=FailureSpec(action=FailurePolicy.RETRY, max_retries=3),
        )

        result = StepExecution(step, sandbox_path=fs.base_path).run()

        assert result.ok is True
        assert result.status == "completed"
        assert result.exit_code == 0
        assert result.attempts == 2
        assert "attempt 2 succeeded" in result.stdout

    def test_explicit_step_env_overrides_wt_metadata(self, fs: FileSystem) -> None:
        """Precedence: explicit step env > WT_* metadata env > ambient env."""
        step = StepDefinition(
            id="override_step",
            type=StepType.COMMAND,
            command='echo "ATTEMPT=$WT_STEP_ATTEMPT"',
            env={"WT_STEP_ATTEMPT": "custom_override"},
        )

        result = StepExecution(step, sandbox_path=fs.base_path, step_index=1, initial_attempt=1).run()

        assert result.ok is True
        assert "ATTEMPT=custom_override" in result.stdout

    def test_template_interpolation_on_command_and_env(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="interpolate_cmd",
            type=StepType.COMMAND,
            command="echo '{{ step.index }}:{{ step.attempt }}'",
            env={"MY_NAME": "{{ step.id }}"},
        )

        result = StepExecution(step, sandbox_path=fs.base_path, step_index=4).run()

        assert result.ok is True
        assert "4:1" in result.stdout

    def test_step_execution_with_historical_steps_env_and_interpolation(self, fs: FileSystem) -> None:
        step = StepDefinition(
            id="third_step",
            type=StepType.COMMAND,
            command='echo "FIRST={{ steps[0].id }} LAST={{ steps[-1].status }} BUILD_CODE={{ steps.build_step.exit_code }} JSON=$WT_STEPS_JSON"',
            env={"STEP0_NAME": "{{ steps[0].name }}"},
        )
        s0 = PreviousStepMetadata(id="setup_step", name="Setup Step", index="1", status="completed", exit_code="0")
        s1 = PreviousStepMetadata(id="build_step", name="Build Step", index="2", status="completed", exit_code="0")

        result = StepExecution(
            step,
            sandbox_path=fs.base_path,
            step_index=3,
            steps=[s0, s1],
        ).run()

        assert result.ok is True
        assert "FIRST=setup_step" in result.stdout
        assert "LAST=completed" in result.stdout
        assert "BUILD_CODE=0" in result.stdout
        assert '"id": "setup_step"' in result.stdout
        assert '"id": "build_step"' in result.stdout
