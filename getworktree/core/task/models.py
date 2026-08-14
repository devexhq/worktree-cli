"""Pydantic models for task blueprint definitions."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

from getworktree.core.step import StepDefinition

_SLUG_RE = re.compile(r"[^\w-]+")


def _slugify_step_id(name: str, idx: int) -> str:
    """Build a step id from a display name, falling back to ``step-{idx}``."""
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or f"step-{idx}"


def _ensure_step_id(step_dict: dict[str, Any], idx: int) -> None:
    """Assign a default ``id`` when missing or empty."""
    existing = step_dict.get("id")
    if existing:
        return
    name_val = step_dict.get("name")
    if isinstance(name_val, str) and name_val.strip():
        step_dict["id"] = _slugify_step_id(name_val, idx)
    else:
        step_dict["id"] = f"step-{idx}"


def _map_command_shorthand(step_dict: dict[str, Any]) -> None:
    """Map bare ``command:`` shorthand onto ``run`` when no mode is set."""
    if "command" not in step_dict:
        return
    if any(key in step_dict for key in ("run", "uses", "type")):
        return
    step_dict["run"] = step_dict.pop("command")


def _normalize_step_item(item: Any, idx: int) -> Any:
    """Normalize one raw step entry for ``StepDefinition`` validation."""
    if not isinstance(item, dict):
        return item
    step_dict = dict(item)
    _ensure_step_id(step_dict, idx)
    _map_command_shorthand(step_dict)
    return step_dict


class TaskDefinition(BaseModel):
    """Model for task blueprint definitions in ``.worktree/catalog/tasks/``."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    name: str
    description: str = ""
    summary: str = ""
    use_sandbox: bool = True
    steps: list[StepDefinition] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _fill_step_shorthand_defaults(cls, data: Any) -> Any:
        """Fill missing step ids and map bare ``command:`` keys before validation."""
        if not isinstance(data, dict):
            return data

        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            return data

        data["steps"] = [_normalize_step_item(item, idx) for idx, item in enumerate(raw_steps, start=1)]
        return data
