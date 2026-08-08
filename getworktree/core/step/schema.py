"""Step definition schema models, enums, and loading helpers."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from getworktree.core.workflows.models import StepAssert


class StepType(StrEnum):
    """Supported step primitive types."""

    COMMAND = "command"
    AGENT = "agent"
    SCRIPT = "script"


class FailureAction(StrEnum):
    """Supported failure handling policies."""

    RETRY = "retry"
    ABORT = "abort"
    IGNORE = "ignore"


class StepNotFoundError(Exception):
    """Raised when a step definition file or ID cannot be found."""


class StepValidationError(Exception):
    """Raised when step definition YAML parsing or schema validation fails."""


class StepDefinition(BaseModel):
    """Model for step definitions stored in .worktree/templates/steps/."""

    model_config = {"extra": "forbid", "strict": True, "populate_by_name": True}

    id: str
    name: str
    type: StepType
    description: str
    command: str | None = None
    prompt: str | None = None
    agent: str | None = None
    tools: list[str] = Field(default_factory=list)
    script_path: str | None = None
    timeout_seconds: int = Field(default=120, gt=0)
    failure_action: FailureAction = FailureAction.ABORT
    assert_: StepAssert | None = Field(default=None, alias="assert")

    @field_validator("type", mode="before")
    @classmethod
    def parse_step_type(cls, val: Any) -> Any:
        """Coerce string value to StepType enum instance."""
        if isinstance(val, str):
            try:
                return StepType(val)
            except ValueError:
                pass
        return val

    @field_validator("failure_action", mode="before")
    @classmethod
    def parse_failure_action(cls, val: Any) -> Any:
        """Coerce string value to FailureAction enum instance."""
        if isinstance(val, str):
            try:
                return FailureAction(val)
            except ValueError:
                pass
        return val

    @model_validator(mode="after")
    def validate_type_fields(self) -> StepDefinition:
        """Enforce required fields based on step primitive type."""
        if self.type == StepType.COMMAND and not self.command:
            raise ValueError("Command steps must specify a non-empty 'command' string.")
        if self.type == StepType.AGENT and not self.prompt:
            raise ValueError("Agent steps must specify a non-empty 'prompt' string.")
        if self.type == StepType.SCRIPT and not self.script_path:
            raise ValueError("Script steps must specify a non-empty 'script_path' string.")
        return self


def load_step_definition(path: Path) -> StepDefinition:
    """Load and validate a StepDefinition from a YAML file.

    Args:
        path: Path to the YAML step definition file.

    Returns:
        Validated StepDefinition instance.

    Raises:
        StepNotFoundError: If the file does not exist or is not a regular file.
        StepValidationError: If YAML parsing fails or schema validation fails.
    """
    path = path.resolve()
    if not path.exists() or not path.is_file():
        raise StepNotFoundError(f"Step definition file not found at '{path}'.")

    try:
        raw_text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except (OSError, yaml.YAMLError) as exc:
        raise StepValidationError(f"Failed to read or parse YAML step definition at '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise StepValidationError(f"Root of step definition YAML at '{path}' must be a mapping object.")

    try:
        return StepDefinition.model_validate(data)
    except (ValidationError, ValueError) as exc:
        raise StepValidationError(f"Step definition validation failed for '{path}': {exc}") from exc


def load_step_by_id(step_id_or_name: str, cwd: Path | None = None) -> StepDefinition:
    """Resolve a StepDefinition from .worktree/templates/steps/ by ID or name.

    Args:
        step_id_or_name: Identifier or name slug of the step.
        cwd: Optional working directory root (defaults to Path.cwd()).

    Returns:
        Resolved StepDefinition instance.

    Raises:
        StepNotFoundError: If step directory does not exist or step is not found.
        StepValidationError: If matching file has schema validation errors.
    """
    root_dir = cwd or Path.cwd()
    steps_dir = root_dir / ".worktree" / "templates" / "steps"

    if not steps_dir.exists() or not steps_dir.is_dir():
        raise StepNotFoundError(f"Step '{step_id_or_name}' not found. Directory '{steps_dir}' does not exist.")

    # Check direct filename match first (<step_id_or_name>.yaml / .yml)
    for ext in (".yaml", ".yml"):
        direct_path = steps_dir / f"{step_id_or_name}{ext}"
        if direct_path.exists() and direct_path.is_file():
            return load_step_definition(direct_path)

    # Scan step files in steps_dir for matching id or name
    for path in sorted(steps_dir.iterdir()):
        if path.is_file() and path.suffix in (".yaml", ".yml"):
            try:
                step = load_step_definition(path)
                if step.id == step_id_or_name or step.name == step_id_or_name:
                    return step
            except StepValidationError:
                # If searching by ID, invalid files will raise when directly selected,
                # but during directory scan we log/ignore unrelated broken files.
                continue

    raise StepNotFoundError(f"Step '{step_id_or_name}' not found in '{steps_dir}'.")
