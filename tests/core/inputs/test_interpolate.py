"""Unit tests for input template interpolation."""

from worktree.core.inputs import interpolate_step_fields, interpolate_string
from worktree.core.step import StepDefinition, StepType


def test_interpolate_string_replaces_placeholders() -> None:
    rendered = interpolate_string(
        "git commit -m '${{ inputs.message }}' flag=${{ inputs.allow_empty }}",
        {"message": "ship it", "allow_empty": False},
    )
    assert rendered == "git commit -m 'ship it' flag=False"


def test_interpolate_string_keeps_unknown_placeholders() -> None:
    template = "echo ${{ inputs.missing }}"
    assert interpolate_string(template, {"other": "x"}) == template


def test_interpolate_step_fields_updates_command_and_env() -> None:
    step = StepDefinition(
        id="s1",
        type=StepType.COMMAND,
        command="echo ${{ inputs.message }}",
        env={"MSG": "${{ inputs.message }}", "STATIC": "keep"},
    )

    updated = interpolate_step_fields(step, {"message": "hello"})
    assert updated.command == "echo hello"
    assert updated.env == {"MSG": "hello", "STATIC": "keep"}


def test_interpolate_step_fields_updates_prompt_and_script_path() -> None:
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


def test_interpolate_step_fields_noop_without_inputs() -> None:
    step = StepDefinition(id="s1", type=StepType.COMMAND, command="echo hi")
    assert interpolate_step_fields(step, {}) is step
