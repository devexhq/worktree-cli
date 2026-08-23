"""Unit tests for input template interpolation."""

from __future__ import annotations

from worktree.core.inputs import interpolate_step_fields, interpolate_string
from worktree.core.step import StepDefinition, StepType


class InputInterpolateTests:
    """Unit tests for template interpolation in strings and step definitions."""

    def test_interpolate_string_replaces_placeholders(self) -> None:
        rendered = interpolate_string(
            "git commit -m '${{ inputs.message }}' flag=${{ inputs.allow_empty }}",
            {"message": "ship it", "allow_empty": False},
        )
        assert rendered == "git commit -m 'ship it' flag=False"

    def test_interpolate_string_keeps_unknown_placeholders(self) -> None:
        template = "echo ${{ inputs.missing }}"
        assert interpolate_string(template, {"other": "x"}) == template

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

    def test_interpolate_step_fields_updates_prompt_and_script_path(self) -> None:
        prompt_step = StepDefinition(
            id="agent",
            type=StepType.AGENT,
            prompt="do ${{ inputs.message }}",
        )
        script_step = StepDefinition(
            id="script",
            type=StepType.SCRIPT,
            script_path="scripts/${{ inputs.message }}.sh",
        )

        assert interpolate_step_fields(prompt_step, {"message": "hello"}).prompt == "do hello"
        assert interpolate_step_fields(script_step, {"message": "hello"}).script_path == "scripts/hello.sh"

    def test_interpolate_step_fields_noop_without_inputs(self) -> None:
        step = StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi")
        assert interpolate_step_fields(step, {}) is step
