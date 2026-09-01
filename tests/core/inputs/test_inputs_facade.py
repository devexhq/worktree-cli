"""Tests for Inputs domain facade."""

from __future__ import annotations

from worktree.core.inputs import (
    InputResolveResult,
    Inputs,
    InputType,
    ParameterInput,
)
from worktree.core.step import StepDefinition


def test_inputs_facade_parse_and_resolve():
    declarations = {
        "env": ParameterInput(type=InputType.STRING, default="staging", aliases=["--env", "-e"]),
        "count": ParameterInput(type=InputType.INTEGER, default=1, aliases=["--count"]),
        "debug": ParameterInput(type=InputType.BOOLEAN, default=False, aliases=["--debug"]),
    }

    parsed = Inputs.parse_cli_args(["--env", "production", "--count", "5", "--debug"], declarations)
    assert isinstance(parsed, InputResolveResult)
    assert parsed.values["env"] == "production"
    assert parsed.values["count"] == 5
    assert parsed.values["debug"] is True

    resolved = Inputs.resolve(
        declarations,
        cli_args=["--env", "prod", "--count", "10", "--debug"],
    )
    assert isinstance(resolved, InputResolveResult)
    assert resolved.values["env"] == "prod"
    assert resolved.values["count"] == 10
    assert resolved.values["debug"] is True


def test_inputs_facade_coerce_and_interpolate():
    val = Inputs.coerce("123", InputType.INTEGER, name="count")
    assert val == 123

    res_str = Inputs.interpolate("Hello ${{ inputs.name }}!", inputs={"name": "World"})
    assert res_str == "Hello World!"

    step_def = StepDefinition(id="step-1", run="echo ${{ inputs.msg }}")
    interp_step = Inputs.interpolate_step(step_def, inputs={"msg": "interp-ok"})
    assert interp_step.run == "echo interp-ok"


def test_inputs_facade_format_helpers():
    declarations = {"my_param": ParameterInput(type=InputType.STRING, default="default_val", required=True)}
    spec = Inputs.format_spec("my_param", declarations["my_param"])
    assert "default='default_val'" in spec

    missing_err = Inputs.format_missing_error(
        kind="workflow",
        name="test-flow",
        missing=["my_param"],
        declarations=declarations,
    )
    assert "Missing required input" in missing_err

    res = InputResolveResult(errors=["Invalid parameter type"])
    err = Inputs.format_error(
        kind="workflow",
        name="test-flow",
        result=res,
        declarations=declarations,
    )
    assert "Invalid parameter type" in err
