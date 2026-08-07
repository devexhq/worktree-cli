"""Pydantic models for full workflow definition V1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

WorkflowContextInclude = Literal["trigger_output", "changed_files", "relevant_source"]


class WorkflowInput(BaseModel):
    """Execution input parameter declaration."""

    model_config = {"extra": "forbid", "strict": True}

    description: str | None = None
    required: bool = False
    default: Any = None


class StepAssert(BaseModel):
    """Declarative verification criteria for standard steps."""

    model_config = {"extra": "forbid", "strict": True}

    exit_code: int | None = None
    output_contains: str | list[str] | None = None
    output_not_contains: str | list[str] | None = None
    regex_match: str | None = None
    json_match: dict[str, Any] | None = None


class StandardStepDefinition(BaseModel):
    """Standard step execution definition (uses catalog step or run shell command)."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    id: str = Field(default="", min_length=0)
    name: str | None = None
    uses: str | None = None
    run: str | None = None
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")
    agent: str | dict[str, Any] | None = None
    prompt: str | None = None
    tools: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, ge=1)
    assert_: StepAssert | None = Field(default=None, alias="assert")
    on_failure: str | dict[str, Any] = "abort"

    @model_validator(mode="after")
    def validate_uses_and_run_mutual_exclusivity(self) -> StandardStepDefinition:
        """Enforce mutual exclusivity between 'uses' and 'run' when specified."""
        if self.uses is not None and self.run is not None:
            raise ValueError(f"Cannot specify both 'uses' and 'run' in step '{self.id or self.name or 'unknown'}'")
        if self.uses is None and self.run is None and (self.id or self.name):
            raise ValueError(f"Step '{self.id or self.name or 'unknown'}' must specify either 'uses' or 'run'")
        return self


class LoopStepBlock(BaseModel):
    """Loop block step execution definition."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    id: str = Field(min_length=1)
    type: Literal["loop"]
    max_iterations: int = Field(default=5, ge=1)
    until: list[str] = Field(min_length=1)
    do: list[StandardStepDefinition] = Field(min_length=1)
    on_max_iterations: str | dict[str, Any] = "prompt_user"


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
    steps: list[StandardStepDefinition | LoopStepBlock] | None = None

    @model_validator(mode="after")
    def validate_workflow(self) -> WorkflowDefinition:
        """Enforce workflow version and ID defaults."""
        str_val = str(self.version)
        if str_val not in ("1", "1.0"):
            raise ValueError("Workflow 'version' must be '1.0' or 1")
        if self.id is None:
            self.id = self.name
        return self
