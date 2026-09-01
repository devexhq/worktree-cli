"""Shared blueprint input declarations, resolution, and interpolation."""

from worktree.core.inputs.facade import Inputs
from worktree.core.inputs.models import InputResolveResult, InputType, ParameterInput
from worktree.core.inputs.services import (
    coerce_input_value,
    format_input_error_message,
    format_input_spec,
    format_missing_inputs_error,
    interpolate_step_fields,
    interpolate_string,
    parse_cli_input_args,
    resolve_inputs,
)

__all__ = [
    "InputResolveResult",
    "InputType",
    "Inputs",
    "ParameterInput",
    "coerce_input_value",
    "format_input_error_message",
    "format_input_spec",
    "format_missing_inputs_error",
    "interpolate_step_fields",
    "interpolate_string",
    "parse_cli_input_args",
    "resolve_inputs",
]
