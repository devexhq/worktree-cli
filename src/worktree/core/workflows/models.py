"""Pydantic models for full workflow definition V1."""

from __future__ import annotations

from enum import StrEnum
from importlib import resources
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from worktree.common.schema_validation import SchemaValidator
from worktree.core.inputs import ParameterInput
from worktree.core.step import (
    BlueprintDefaults,
    LoopStepBlock,
    StepDefinition,
    apply_on_failure_default,
    extract_defaults_on_failure,
)

WORKFLOW_VALIDATOR: SchemaValidator = SchemaValidator(resources.files("worktree.schemas.v1") / "workflow.json")

# Back-compat alias: WorkflowInput is the shared ParameterInput model.
WorkflowInput = ParameterInput


def _normalize_workflow_step_item(item: Any, on_failure_default: Any | None) -> Any:
    """Apply fill-if-omitted defaults.on_failure to top-level standard steps only."""
    if not isinstance(item, dict):
        return item
    return apply_on_failure_default(dict(item), on_failure_default)


class WorkflowDefinition(BaseModel):
    """Full workflow definition V1 model."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    schema_validator: ClassVar[SchemaValidator] = WORKFLOW_VALIDATOR

    version: int | str
    name: str = Field(min_length=1)
    id: str | None = None
    description: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    env: dict[str, str] = Field(default_factory=dict)
    inputs: dict[str, ParameterInput] = Field(default_factory=dict)
    defaults: BlueprintDefaults = Field(default_factory=BlueprintDefaults)
    steps: list[StepDefinition | LoopStepBlock] | None = None

    @model_validator(mode="before")
    @classmethod
    def _apply_blueprint_defaults(cls, data: Any) -> Any:
        """Fill omitted step on_failure from defaults at load/normalize time."""
        if not isinstance(data, dict):
            return data
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            return data
        on_failure_default = extract_defaults_on_failure(data.get("defaults"))
        data["steps"] = [_normalize_workflow_step_item(item, on_failure_default) for item in raw_steps]
        return data

    @model_validator(mode="after")
    def validate_workflow(self) -> WorkflowDefinition:
        """Enforce workflow version and ID defaults."""
        str_val = str(self.version)
        if str_val not in ("1", "1.0"):
            raise ValueError("Workflow 'version' must be '1.0' or 1")
        if self.id is None:
            self.id = self.name
        return self


class WorkflowResumeStatus(StrEnum):
    """Classified outcomes for ``resume_workflow``."""

    OK = "ok"
    NOT_FOUND = "not_found"
    WRONG_STATUS = "wrong_status"
    MISSING_SANDBOX = "missing_sandbox"
    CORRUPT_CHECKPOINT = "corrupt_checkpoint"
    FAILED = "failed"


class WorkflowResumeResult(BaseModel):
    """Non-raising result of resuming a paused workflow session."""

    model_config = {"extra": "forbid", "strict": True}

    status: WorkflowResumeStatus
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when resume completed without errors."""
        return self.status == WorkflowResumeStatus.OK and not self.errors
