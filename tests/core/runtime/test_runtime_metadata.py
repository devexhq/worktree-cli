"""Integration tests for multi-step runtime metadata propagation and previous_step state."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.core.runtime import (
    FailurePromptDecision,
    RunContext,
    run_steps,
)
from worktree.core.step import (
    FailurePolicy,
    FailureSpec,
    StepDefinition,
    StepResult,
    StepType,
)


class _ScriptedPrompter:
    def __init__(self, decisions: list[FailurePromptDecision]) -> None:
        self.decisions = list(decisions)

    def prompt_step_failure(
        self,
        *,
        step: StepDefinition,
        result: StepResult,
        diagnostic: str,
    ) -> FailurePromptDecision:
        return self.decisions.pop(0)


class RuntimeMetadataPropagationTests:
    """Tests verifying step index, previous_step handoff, and prompt_user retry attempt tracking."""

    def test_first_step_has_empty_previous_step_metadata(self, fs: FileSystem) -> None:
        context = RunContext(
            steps=[
                StepDefinition(
                    id="first_step",
                    type=StepType.COMMAND,
                    command='echo "PREV_ID=[$WT_PREVIOUS_STEP_ID] PREV_STATUS=[$WT_PREVIOUS_STEP_STATUS]"',
                )
            ],
            cwd=fs.base_path,
            use_sandbox=False,
        )

        outcome = run_steps(context)
        assert outcome.ok is True
        assert len(outcome.step_results) == 1
        assert "PREV_ID=[] PREV_STATUS=[]" in outcome.step_results[0].stdout

    def test_two_step_run_propagates_previous_step_metadata(self, fs: FileSystem) -> None:
        context = RunContext(
            steps=[
                StepDefinition(
                    id="setup_step",
                    name="Setup Step",
                    type=StepType.COMMAND,
                    command="echo 'setup done'",
                ),
                StepDefinition(
                    id="verify_step",
                    name="Verify Step",
                    type=StepType.COMMAND,
                    command='echo "PREV_ID=$WT_PREVIOUS_STEP_ID PREV_NAME=$WT_PREVIOUS_STEP_NAME PREV_IDX=$WT_PREVIOUS_STEP_INDEX PREV_STATUS=$WT_PREVIOUS_STEP_STATUS PREV_EXIT=$WT_PREVIOUS_STEP_EXIT_CODE"',
                ),
            ],
            cwd=fs.base_path,
            use_sandbox=False,
        )

        outcome = run_steps(context)
        assert outcome.ok is True
        assert len(outcome.step_results) == 2
        step2_out = outcome.step_results[1].stdout
        assert "PREV_ID=setup_step" in step2_out
        assert "PREV_NAME=Setup Step" in step2_out
        assert "PREV_IDX=1" in step2_out
        assert "PREV_STATUS=completed" in step2_out
        assert "PREV_EXIT=0" in step2_out

    def test_previous_step_status_reflects_ignored_on_continue(self, fs: FileSystem) -> None:
        context = RunContext(
            steps=[
                StepDefinition(
                    id="failing_step",
                    name="Failing Step",
                    type=StepType.COMMAND,
                    command="exit 3",
                    on_failure=FailureSpec(action=FailurePolicy.CONTINUE),
                ),
                StepDefinition(
                    id="next_step",
                    type=StepType.COMMAND,
                    command='echo "PREV_ID=$WT_PREVIOUS_STEP_ID PREV_STATUS=$WT_PREVIOUS_STEP_STATUS PREV_EXIT=$WT_PREVIOUS_STEP_EXIT_CODE"',
                ),
            ],
            cwd=fs.base_path,
            use_sandbox=False,
        )

        outcome = run_steps(context)
        assert outcome.ok is True
        assert len(outcome.step_results) == 2
        assert outcome.step_results[0].status == "ignored"

        step2_out = outcome.step_results[1].stdout
        assert "PREV_ID=failing_step" in step2_out
        assert "PREV_STATUS=ignored" in step2_out
        assert "PREV_EXIT=0" in step2_out

    def test_prompt_user_retry_increments_attempt_counter(self, fs: FileSystem) -> None:
        """Verify prompt_user RETRY increments WT_STEP_ATTEMPT from 1 to 2."""
        prompter = _ScriptedPrompter([FailurePromptDecision.RETRY])
        context = RunContext(
            steps=[
                StepDefinition(
                    id="retry_on_prompt",
                    type=StepType.COMMAND,
                    command='if [ "$WT_STEP_ATTEMPT" -eq 1 ]; then echo "fail1" >&2; exit 1; else echo "success2"; exit 0; fi',
                    on_failure=FailureSpec(action=FailurePolicy.PROMPT_USER),
                )
            ],
            cwd=fs.base_path,
            use_sandbox=False,
            failure_prompter=prompter,
        )

        outcome = run_steps(context)
        assert outcome.ok is True
        assert len(outcome.step_results) == 1
        result = outcome.step_results[0]
        assert result.ok is True
        assert result.attempts == 2
        assert "success2" in result.stdout
