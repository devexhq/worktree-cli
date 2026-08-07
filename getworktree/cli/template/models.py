"""Outcome model for ``wt templates`` CLI command."""

from __future__ import annotations

from pydantic import BaseModel, Field

from getworktree.core.templates.models import BuiltinTemplate, TemplateType


class TemplatesCommandOutcome(BaseModel):
    """Outcome model returned by ``templates_list_command``."""

    model_config = {"extra": "forbid", "strict": True}

    templates: list[BuiltinTemplate] = Field(default_factory=list)
    type_filter: TemplateType | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when template listing succeeded."""
        return not self.errors


class TemplateShowCommandOutcome(BaseModel):
    """Outcome model returned by ``template_show_command``."""

    model_config = {"extra": "forbid", "strict": True}

    template: BuiltinTemplate | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when template detail retrieval succeeded."""
        return not self.errors and self.template is not None
