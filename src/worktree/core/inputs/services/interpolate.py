"""Template variable interpolation for resolved blueprint inputs."""

from __future__ import annotations

import re
from typing import Any

_INPUT_PLACEHOLDER_RE = re.compile(r"\$\{\{\s*inputs\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_INTERPOLATED_FIELDS = ("command", "prompt", "script_path", "run")


def interpolate_string(template: str, inputs: dict[str, str | int | bool]) -> str:
    """Replace ``${{ inputs.<name> }}`` placeholders with resolved string values."""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in inputs:
            return match.group(0)
        return str(inputs[key])

    return _INPUT_PLACEHOLDER_RE.sub(_replace, template)


def _interpolated_field_updates(step: Any, inputs: dict[str, str | int | bool]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for field_name in _INTERPOLATED_FIELDS:
        value = getattr(step, field_name, None)
        if isinstance(value, str) and value:
            updates[field_name] = interpolate_string(value, inputs)
    return updates


def _interpolated_env(step: Any, inputs: dict[str, str | int | bool]) -> dict[str, str] | None:
    env = getattr(step, "env", None)
    if not isinstance(env, dict) or not env:
        return None
    new_env = {
        key: interpolate_string(value, inputs) if isinstance(value, str) else value for key, value in env.items()
    }
    return new_env if new_env != env else None


def interpolate_step_fields(
    step: Any,
    inputs: dict[str, str | int | bool],
) -> Any:
    """Return a copy of ``step`` with interpolatable string fields substituted.

    Supports ``command``, ``prompt``, ``script_path``, ``run``, and string values
    inside ``env``. Unknown attributes are left untouched.
    """
    if not inputs:
        return step

    updates = _interpolated_field_updates(step, inputs)
    new_env = _interpolated_env(step, inputs)
    if new_env is not None:
        updates["env"] = new_env
    if not updates:
        return step
    return step.model_copy(update=updates)
