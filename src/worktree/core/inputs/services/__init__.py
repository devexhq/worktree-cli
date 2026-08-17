"""Input domain services: CLI resolution, interpolation, and rendering."""

from worktree.core.inputs.services.interpolate import (
    interpolate_step_fields,
    interpolate_string,
)
from worktree.core.inputs.services.renderer import format_input_spec
from worktree.core.inputs.services.resolve import (
    coerce_input_value,
    format_missing_inputs_error,
    parse_cli_input_args,
    resolve_inputs,
)

__all__ = [
    "coerce_input_value",
    "format_input_spec",
    "format_missing_inputs_error",
    "interpolate_step_fields",
    "interpolate_string",
    "parse_cli_input_args",
    "resolve_inputs",
]
