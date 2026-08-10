"""Pydantic models for full workflow definition V1."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from getworktree.core.step import LoopStepBlock, StepDefinition


class WorkflowInput(BaseModel):
    """Execution input parameter declaration."""

    model_config = {"extra": "forbid", "strict": True}

    description: str | None = None
    required: bool = False
    default: Any = None


class WorkflowDefinition(BaseModel):
    """Full workflow definition V1 model."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    version: int | str
    name: str = Field(min_length=1)
    id: str | None = None
    description: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    env: dict[str, str] = Field(default_factory=dict)
    inputs: dict[str, WorkflowInput] = Field(default_factory=dict)
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
