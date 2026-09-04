"""Unit tests for the merged StepDefinition/LoopStepBlock models and failure vocabulary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from worktree.core.step import (
    BlueprintDefaults,
    FailurePolicy,
    FailureSpec,
    LoopStepBlock,
    StepAssert,
    StepDefinition,
    StepType,
    apply_on_failure_default,
)


class FailurePolicyModelTests:
    """Unit tests for FailurePolicy, FailureSpec, and default propagation."""

    def test_failure_policy_context_terminal_excludes_retry(self) -> None:
        assert FailurePolicy.context("terminal") == {
            FailurePolicy.ABORT,
            FailurePolicy.CONTINUE,
            FailurePolicy.PROMPT_USER,
        }

    def test_failure_policy_context_other_returns_full_set(self) -> None:
        assert FailurePolicy.context("anything-else") == set(FailurePolicy)

    def test_failure_spec_defaults(self) -> None:
        spec = FailureSpec(action=FailurePolicy.ABORT)
        assert spec.max_retries == 3
        assert spec.backoff_ms == 0
        assert spec.on_max_retries == FailurePolicy.ABORT

    def test_failure_spec_coerces_string_actions(self) -> None:
        spec = FailureSpec.model_validate({"action": "retry", "on_max_retries": "continue"})
        assert spec.action == FailurePolicy.RETRY
        assert spec.on_max_retries == FailurePolicy.CONTINUE

    def test_failure_spec_rejects_retry_on_max_retries(self) -> None:
        with pytest.raises(ValidationError, match="on_max_retries must be one of"):
            FailureSpec(action=FailurePolicy.RETRY, on_max_retries=FailurePolicy.RETRY)

    def test_failure_spec_forbids_extra_keys(self) -> None:
        with pytest.raises(ValidationError):
            FailureSpec.model_validate(
                {
                    "action": FailurePolicy.ABORT,
                    "unknown_key": "nope",
                }
            )

    def test_blueprint_defaults_coerces_string_on_failure(self) -> None:
        defaults = BlueprintDefaults.model_validate({"on_failure": "continue"})
        assert defaults.on_failure is not None
        assert defaults.on_failure.action == FailurePolicy.CONTINUE

    def test_blueprint_defaults_forbids_extra_keys(self) -> None:
        with pytest.raises(ValidationError):
            BlueprintDefaults.model_validate({"on_failure": "abort", "extra": True})

    def test_apply_on_failure_default_fill_if_omitted_only(self) -> None:
        filled = apply_on_failure_default({"id": "a", "run": "true"}, "continue")
        assert filled["on_failure"] == "continue"

        from_spec = apply_on_failure_default(
            {"id": "a", "run": "true"},
            FailureSpec(action=FailurePolicy.CONTINUE),
        )
        assert from_spec["on_failure"] == {
            "action": "continue",
            "max_retries": 3,
            "backoff_ms": 0,
            "on_max_retries": "abort",
        }

        explicit = apply_on_failure_default(
            {"id": "b", "run": "true", "on_failure": "abort"},
            "continue",
        )
        assert explicit["on_failure"] == "abort"

        loop = apply_on_failure_default(
            {"id": "loop", "type": "loop", "until": ["x"], "do": []},
            "continue",
        )
        assert "on_failure" not in loop


class StepDefinitionModelTests:
    """Unit tests for StepDefinition field validation, discriminated types, and assertions."""

    def test_step_definition_command_valid(self) -> None:
        step = StepDefinition(
            id="step_pytest",
            name="run-pytest",
            type=StepType.COMMAND,
            description="Run pytest suite",
            command="pytest tests/",
            timeout_seconds=60,
            on_failure=FailureSpec(action=FailurePolicy.ABORT),
        )
        assert step.id == "step_pytest"
        assert step.type == StepType.COMMAND
        assert step.command == "pytest tests/"
        assert step.timeout_seconds == 60
        assert step.on_failure == FailureSpec(action=FailurePolicy.ABORT)

    def test_step_definition_agent_valid(self) -> None:
        step = StepDefinition(
            id="step_refactor",
            name="refactor-code",
            type=StepType.AGENT,
            description="Refactor code for performance",
            prompt="Refactor loop logic",
            tools=["edit_file", "run_linter"],
        )
        assert step.type == StepType.AGENT
        assert step.prompt == "Refactor loop logic"
        assert step.tools == ["edit_file", "run_linter"]

    def test_step_definition_script_valid(self) -> None:
        step = StepDefinition(
            id="step_script",
            name="run-script",
            type=StepType.SCRIPT,
            description="Run custom script",
            script_path="scripts/build.sh",
        )
        assert step.type == StepType.SCRIPT
        assert step.script_path == "scripts/build.sh"

    def test_step_definition_run_shorthand_valid(self) -> None:
        step = StepDefinition(id="step_run", run="pytest tests/ -q")
        assert step.run == "pytest tests/ -q"
        assert step.uses is None
        assert step.type is None

    def test_step_definition_uses_valid(self) -> None:
        step = StepDefinition(id="step_uses", uses="wt/ai-code-patcher")
        assert step.uses == "wt/ai-code-patcher"

    def test_step_definition_on_failure_object_form(self) -> None:
        step = StepDefinition.model_validate(
            {
                "id": "step_retry",
                "run": "flaky-command",
                "on_failure": {"action": "retry", "max_retries": 5, "backoff_ms": 250, "on_max_retries": "continue"},
            }
        )
        assert step.on_failure.action == FailurePolicy.RETRY
        assert step.on_failure.max_retries == 5
        assert step.on_failure.backoff_ms == 250
        assert step.on_failure.on_max_retries == FailurePolicy.CONTINUE

    def test_step_definition_missing_required_type_fields(self) -> None:
        with pytest.raises(ValidationError, match="Command steps must specify"):
            StepDefinition(id="s1", type=StepType.COMMAND)

        with pytest.raises(ValidationError, match="Agent steps must specify"):
            StepDefinition(id="s2", type=StepType.AGENT)

        with pytest.raises(ValidationError, match="Script steps must specify"):
            StepDefinition(id="s3", type=StepType.SCRIPT)

    def test_step_definition_none_of_run_uses_type_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must specify one of 'run', 'uses', or 'type'"):
            StepDefinition(id="s1")

    def test_step_definition_run_combined_with_uses_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot be combined with"):
            StepDefinition(id="s1", run="pytest", uses="wt/run-tests")

    def test_step_definition_run_combined_with_type_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot be combined with"):
            StepDefinition(id="s1", run="pytest", type=StepType.COMMAND, command="pytest")

    def test_step_definition_extra_keys_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            StepDefinition.model_validate(
                {
                    "id": "s1",
                    "type": StepType.COMMAND,
                    "command": "echo 1",
                    "unknown_key": "invalid",
                }
            )

    def test_step_definition_assert_alias_round_trip(self) -> None:
        """``assert`` YAML key maps to ``assert_`` and serializes back under ``assert``."""
        step = StepDefinition.model_validate(
            {
                "id": "step_build",
                "type": "command",
                "command": "make build",
                "assert": {
                    "exit_code": [0, 1],
                    "file_exists": ["dist/app.bin", "dist/manifest.json"],
                    "file_not_exists": "tmp/lock",
                    "file_not_empty": "dist/app.bin",
                },
            }
        )

        dumped = step.model_dump(by_alias=True)
        assert "assert_" not in dumped
        assert dumped["assert"]["exit_code"] == [0, 1]

        reloaded = StepDefinition.model_validate(dumped)
        assert reloaded.assert_ is not None
        assert reloaded.assert_.exit_code == [0, 1]
        assert reloaded.assert_.file_exists == ["dist/app.bin", "dist/manifest.json"]

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("file_exists", "/etc/passwd"),
            ("file_exists", "../secrets.txt"),
            ("file_exists", ["dist/app.bin", "a/../../x"]),
            ("file_exists", ""),
            ("file_not_exists", "C:/Windows/system32"),
            ("file_not_empty", "\\..\\escape.txt"),
        ],
    )
    def test_step_definition_assert_path_safety_rejects_unsafe_paths(
        self, field_name: str, value: str | list[str]
    ) -> None:
        with pytest.raises(ValidationError, match=field_name):
            StepDefinition(
                id="step_build",
                type=StepType.COMMAND,
                command="make build",
                assert_=StepAssert.model_validate({field_name: value}),
            )


class LoopStepBlockModelTests:
    """Unit tests for LoopStepBlock schema and loop validation rules."""

    def test_loop_step_block_defaults(self) -> None:
        block = LoopStepBlock(
            id="dev-cycle",
            type="loop",
            until=["steps.run-tests.exit_code == 0"],
            do=[StepDefinition(id="run-tests", run="pytest")],
        )
        assert block.max_iterations == 5
        assert block.on_max_iterations == FailurePolicy.PROMPT_USER

    def test_loop_step_block_rejects_retry_on_max_iterations(self) -> None:
        with pytest.raises(ValidationError, match="on_max_iterations must be one of"):
            LoopStepBlock(
                id="dev-cycle",
                type="loop",
                until=["steps.run-tests.exit_code == 0"],
                do=[StepDefinition(id="run-tests", run="pytest")],
                on_max_iterations=FailurePolicy.RETRY,
            )
