"""Models for built-in workflow, task, and step templates."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TemplateType(StrEnum):
    """Supported built-in template types."""

    WORKFLOW = "workflow"
    TASK = "task"
    STEP = "step"


class BuiltinTemplate(BaseModel):
    """Metadata for one wt-defined built-in template."""

    model_config = {"extra": "forbid", "strict": True}

    name: str
    type: TemplateType
    description: str
    summary: str


class BuiltinTemplateResult(BaseModel):
    """Result of listing built-in templates."""

    model_config = {"extra": "forbid", "strict": True}

    templates: list[BuiltinTemplate] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when discovery/loading succeeded without fatal errors."""
        return not self.errors
