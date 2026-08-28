"""Unified Pydantic models for task and workflow blueprint documents."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from worktree.core.blueprint.exceptions import BlueprintValidationError
from worktree.core.db import BlueprintKind, RunRecord
from worktree.core.inputs import ParameterInput
from worktree.core.step import (
    BlueprintDefaults,
    LoopStepBlock,
    StepDefinition,
    apply_on_failure_default,
    extract_defaults_on_failure,
    validate_condition_expression,
)

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


def _normalize_step_item(item: Any, idx: int, on_failure_default: Any | None = None) -> Any:
    """Normalize one raw step entry for ``StepDefinition`` validation."""
    if not isinstance(item, dict):
        return item
    step_dict = dict(item)
    _ensure_step_id(step_dict, idx)
    _map_command_shorthand(step_dict)
    return apply_on_failure_default(step_dict, on_failure_default)


def _validate_single_loop_block(loop: LoopStepBlock) -> None:
    known = {s.id for s in loop.do}
    for expr in loop.until:
        errors = validate_condition_expression(expr, known_step_ids=known)
        if errors:
            raise ValueError(f"Loop '{loop.id}': {'; '.join(errors)}")


def _validate_loop_steps(steps: list[StepDefinition | LoopStepBlock]) -> None:
    for step in steps:
        if isinstance(step, LoopStepBlock):
            _validate_single_loop_block(step)


class BlueprintDefinition(BaseModel):
    """Unified task/workflow document. ``kind`` is injected, never read from YAML."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    kind: BlueprintKind
    name: str = Field(min_length=1)
    description: str = ""
    summary: str = ""
    id: str | None = None
    version: int | str = 1
    use_sandbox: bool = True
    timeout_seconds: int | None = Field(default=None, ge=1)
    env: dict[str, str] = Field(default_factory=dict)
    inputs: dict[str, ParameterInput] = Field(default_factory=dict)
    defaults: BlueprintDefaults = Field(default_factory=BlueprintDefaults)
    steps: list[StepDefinition | LoopStepBlock] = Field(default_factory=list)

    @classmethod
    def from_document(cls, raw: dict[str, Any], *, kind: BlueprintKind) -> BlueprintDefinition:
        """Validate a YAML object after injecting ``kind`` and dropping any authored ``kind``."""
        if not isinstance(raw, dict):
            raise BlueprintValidationError("Blueprint document must be a mapping.")
        payload = dict(raw)
        payload.pop("kind", None)
        payload["kind"] = kind
        try:
            return cls.model_validate(payload)
        except (ValidationError, ValueError) as exc:
            raise BlueprintValidationError(f"Blueprint definition validation failed for kind='{kind}': {exc}") from exc

    @field_validator("description", "summary", mode="before")
    @classmethod
    def _coerce_blank_text(cls, value: Any) -> Any:
        """Treat JSON/YAML null as an empty string."""
        return "" if value is None else value

    @model_validator(mode="before")
    @classmethod
    def _fill_step_shorthand_defaults(cls, data: Any) -> Any:
        """Fill missing step ids, map bare ``command:``, and inherit defaults.on_failure."""
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            return payload

        on_failure_default = extract_defaults_on_failure(payload.get("defaults"))
        payload["steps"] = [
            _normalize_step_item(item, idx, on_failure_default) for idx, item in enumerate(raw_steps, start=1)
        ]
        return payload

    @model_validator(mode="after")
    def _apply_kind_rules(self) -> BlueprintDefinition:
        """Default ``id`` to ``name``, reject loop steps on tasks, and validate loop conditions."""
        if self.id is None:
            self.id = self.name
        if self.kind == BlueprintKind.TASK and any(isinstance(step, LoopStepBlock) for step in self.steps):
            raise ValueError("kind=task cannot contain loop steps")
        _validate_loop_steps(self.steps)
        return self


class BlueprintRunCommandOutcome(BaseModel):
    """Unified outcome for task and workflow execution."""

    model_config = {"extra": "forbid", "strict": True}

    run_record: RunRecord | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if run completed without fatal errors."""
        return self.run_record is not None and len(self.errors) == 0
