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

    def test_multi_step_run_propagates_historical_steps_metadata(self, fs: FileSystem) -> None:
        """Verify steps[0], steps[-1], steps.<id>, WT_STEPS_JSON, and in-flight exclusion across 3 steps."""
        context = RunContext(
            steps=[
                StepDefinition(
                    id="step_a",
                    name="Step Alpha",
                    type=StepType.COMMAND,
                    command='echo "A_STEPS=[{{ steps[0].id }}] A_JSON=$WT_STEPS_JSON"',
                ),
                StepDefinition(
                    id="step_b",
                    name="Step Beta",
                    type=StepType.COMMAND,
                    command='echo "B_FIRST={{ steps[0].id }} B_LAST={{ steps[-1].id }} B_A_STAT={{ steps.step_a.status }} B_JSON=$WT_STEPS_JSON"',
                ),
                StepDefinition(
                    id="step_c",
                    name="Step Gamma",
                    type=StepType.COMMAND,
                    command='echo "C_FIRST={{ steps[0].id }} C_SECOND={{ steps[1].id }} C_LAST={{ steps[-1].id }} C_PREV={{ previous_step.id }} C_JSON=$WT_STEPS_JSON"',
                ),
            ],
            cwd=fs.base_path,
            use_sandbox=False,
        )

        outcome = run_steps(context)
        assert outcome.ok is True
        assert len(outcome.step_results) == 3

        # Step A: no prior finished steps; in-flight step_a is NOT in steps
        out_a = outcome.step_results[0].stdout
        assert "A_STEPS=[]" in out_a
        assert "A_JSON=[]" in out_a

        # Step B: step_a finished; in-flight step_b is NOT in steps
        out_b = outcome.step_results[1].stdout
        assert "B_FIRST=step_a" in out_b
        assert "B_LAST=step_a" in out_b
        assert "B_A_STAT=completed" in out_b
        assert '"id": "step_a"' in out_b
        assert "step_b" not in out_b.split("B_JSON=")[1]

        # Step C: step_a and step_b finished; steps[-1] == previous_step == step_b
        out_c = outcome.step_results[2].stdout
        assert "C_FIRST=step_a" in out_c
        assert "C_SECOND=step_b" in out_c
        assert "C_LAST=step_b" in out_c
        assert "C_PREV=step_b" in out_c
        assert '"id": "step_a"' in out_c
        assert '"id": "step_b"' in out_c
        assert "step_c" not in out_c.split("C_JSON=")[1]
