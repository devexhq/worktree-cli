"""Template variable interpolation for resolved blueprint inputs and execution metadata."""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\$?\{\{\s*([^}]+?)\s*\}\}")
_INTERPOLATED_FIELDS = ("command", "prompt", "script_path", "run")
_STEP_ENTRY_FIELDS = {"id", "name", "index", "status", "exit_code"}
_STEPS_BRACKET_RE = re.compile(r"^steps\s*\[\s*(['\"]?)(.*?)\1\s*\]\s*\.\s*([A-Za-z0-9_]+)$")

_METADATA_EXTRACTORS: dict[str, Any] = {
    "step.id": lambda meta: str(meta.step.id),
    "step.name": lambda meta: str(meta.step.name),
    "step.index": lambda meta: str(meta.step.index),
    "step.attempt": lambda meta: str(meta.step.attempt),
    "task.name": lambda meta: str(meta.task.name),
    "task.sha": lambda meta: str(meta.task.sha),
    "workflow.name": lambda meta: str(meta.workflow.name),
    "workflow.sha": lambda meta: str(meta.workflow.sha),
    "previous_step.id": lambda meta: str(meta.previous_step.id),
    "previous_step.name": lambda meta: str(meta.previous_step.name),
    "previous_step.index": lambda meta: str(meta.previous_step.index),
    "previous_step.status": lambda meta: str(meta.previous_step.status),
    "previous_step.exit_code": lambda meta: str(meta.previous_step.exit_code),
}


def _parse_steps_selector(key: str) -> tuple[str, str, bool] | None:
    """Parse a steps expression into (selector, field_name, is_quoted)."""
    bracket_match = _STEPS_BRACKET_RE.match(key)
    if bracket_match:
        quote = bracket_match.group(1)
        selector = bracket_match.group(2).strip()
        field_name = bracket_match.group(3)
        return selector, field_name, bool(quote)

    if key.startswith("steps."):
        parts = key.split(".")
        if len(parts) >= 3:
            field_name = parts[-1]
            selector = ".".join(parts[1:-1])
            return selector, field_name, False

    return None


def _resolve_step_entry_field(entry: Any | None, field_name: str) -> str:
    if entry is None:
        return ""
    value = getattr(entry, field_name, "")
    return str(value) if value is not None else ""


def _find_step_by_id(steps: list[Any], step_id: str) -> Any | None:
    for entry in reversed(steps):
        if getattr(entry, "id", None) == step_id:
            return entry
    return None


def _resolve_steps_placeholder(key: str, metadata: Any) -> tuple[bool, str]:
    parsed = _parse_steps_selector(key)
    if parsed is None:
        return False, ""

    selector, field_name, is_quoted = parsed
    if field_name not in _STEP_ENTRY_FIELDS:
        return False, ""

    steps_list = getattr(metadata, "steps", None) or []

    if not is_quoted:
        try:
            index = int(selector)
            if 0 <= index < len(steps_list) or (index < 0 and abs(index) <= len(steps_list)):
                entry = steps_list[index]
                return True, _resolve_step_entry_field(entry, field_name)
            return True, ""
        except ValueError:
            pass

    entry = _find_step_by_id(steps_list, selector)
    return True, _resolve_step_entry_field(entry, field_name)


def _resolve_metadata_placeholder(key: str, metadata: Any) -> tuple[bool, str]:
    extractor = _METADATA_EXTRACTORS.get(key)
    if extractor is not None:
        try:
            return True, extractor(metadata)
        except AttributeError:
            pass
    if key.startswith("steps[") or key.startswith("steps."):
        return _resolve_steps_placeholder(key, metadata)
    return False, ""


def _resolve_input_placeholder(key: str, inputs: dict[str, Any]) -> tuple[bool, str]:
    if key.startswith("inputs."):
        input_name = key[7:]
        if input_name in inputs:
            return True, str(inputs[input_name])
    if key in inputs:
        return True, str(inputs[key])
    return False, ""


def _resolve_placeholder(
    key: str,
    inputs: dict[str, Any] | None,
    metadata: Any | None,
) -> tuple[bool, str]:
    if metadata is not None:
        found, val = _resolve_metadata_placeholder(key, metadata)
        if found:
            return True, val
    if inputs is not None:
        found, val = _resolve_input_placeholder(key, inputs)
        if found:
            return True, val
    return False, ""


def interpolate_string(
    template: str,
    inputs: dict[str, Any] | None = None,
    metadata: Any | None = None,
) -> str:
    """Replace ``${{ ... }}`` and ``{{ ... }}`` placeholders with resolved string values."""
    if not inputs and metadata is None:
        return template

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        found, value = _resolve_placeholder(key, inputs, metadata)
        if not found:
            return match.group(0)
        return value

    return _PLACEHOLDER_RE.sub(_replace, template)


def _interpolated_field_updates(
    step: Any,
    inputs: dict[str, Any] | None = None,
    metadata: Any | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for field_name in _INTERPOLATED_FIELDS:
        value = getattr(step, field_name, None)
        if isinstance(value, str) and value:
            interpolated = interpolate_string(value, inputs=inputs, metadata=metadata)
            if interpolated != value:
                updates[field_name] = interpolated
    return updates


def _interpolated_env(
    step: Any,
    inputs: dict[str, Any] | None = None,
    metadata: Any | None = None,
) -> dict[str, str] | None:
    env = getattr(step, "env", None)
    if not isinstance(env, dict) or not env:
        return None
    new_env = {
        key: interpolate_string(value, inputs=inputs, metadata=metadata) if isinstance(value, str) else value
        for key, value in env.items()
    }
    return new_env if new_env != env else None


def interpolate_step_fields(
    step: Any,
    inputs: dict[str, Any] | None = None,
    metadata: Any | None = None,
) -> Any:
    """Return a copy of ``step`` with interpolatable string fields substituted.

    Supports ``command``, ``prompt``, ``script_path``, ``run``, and string values
    inside ``env``. Unknown attributes are left untouched.
    """
    if not inputs and metadata is None:
        return step

    updates = _interpolated_field_updates(step, inputs=inputs, metadata=metadata)
    new_env = _interpolated_env(step, inputs=inputs, metadata=metadata)
    if new_env is not None:
        updates["env"] = new_env
    if not updates:
        return step
    return step.model_copy(update=updates)
