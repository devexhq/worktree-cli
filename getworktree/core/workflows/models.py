"""Pydantic models for full workflow definition V1."""

from __future__ import annotations

from importlib import resources
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from getworktree.common.schema_validation import SchemaValidator
from getworktree.core.inputs import ParameterInput
from getworktree.core.step import LoopStepBlock, StepDefinition

WORKFLOW_VALIDATOR: SchemaValidator = SchemaValidator(resources.files("getworktree.schemas.v1") / "workflow.json")

# Back-compat alias: WorkflowInput is the shared ParameterInput model.
WorkflowInput = ParameterInput


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
    steps: list[StepDefinition | LoopStepBlock] | None = None

    @model_validator(mode="after")
    def validate_workflow(self) -> WorkflowDefinition:
        """Enforce workflow version and ID defaults."""
        str_val = str(self.version)
        if str_val not in ("1", "1.0"):
            raise ValueError("Workflow 'version' must be '1.0' or 1")
        if self.id is None:
            self.id = self.name
        return self
