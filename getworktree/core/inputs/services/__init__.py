"""Input domain services: CLI resolution and template interpolation."""

from getworktree.core.inputs.services.interpolate import (
    interpolate_step_fields,
    interpolate_string,
)
from getworktree.core.inputs.services.resolve import (
    coerce_input_value,
    format_missing_inputs_error,
    parse_cli_input_args,
    resolve_inputs,
)

__all__ = [
    "coerce_input_value",
    "format_missing_inputs_error",
    "interpolate_step_fields",
    "interpolate_string",
    "parse_cli_input_args",
    "resolve_inputs",
]
