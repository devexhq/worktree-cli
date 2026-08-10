import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from getworktree.common.models import FailurePolicy, FailureSpec

_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:/")
DEFAULT_STEP_TIMEOUT_SECONDS = 120


class StepType(StrEnum):
    """Supported step primitive types."""

    COMMAND = "command"
    AGENT = "agent"
    SCRIPT = "script"


def _is_unsafe_assert_path(path: str) -> bool:
    """Return True when ``path`` is absolute, empty, or contains a ``..`` segment."""
    normalized = path.replace("\\", "/")
    if not normalized or normalized.startswith("/") or _DRIVE_PATH_RE.match(normalized):
        return True
    return any(part == ".." for part in normalized.split("/"))


def _validate_assert_paths(value: str | list[str] | None, field_name: str) -> None:
    """Reject empty, absolute, or parent-traversal paths in file-system asserts."""
    if value is None:
        return
    entries = [value] if isinstance(value, str) else value
    for entry in entries:
        if _is_unsafe_assert_path(entry):
            raise ValueError(f"{field_name} path must be a non-empty relative path without '..' segments: {entry!r}")


class StepAssert(BaseModel):
    """Declarative verification criteria for standard steps."""

    model_config = {"extra": "forbid", "strict": True}

    exit_code: int | list[int] | None = None
    output_contains: str | list[str] | None = None
    output_not_contains: str | list[str] | None = None
    regex_match: str | None = None
    json_match: dict[str, Any] | None = None
    file_exists: str | list[str] | None = None
    file_not_exists: str | list[str] | None = None
    file_not_empty: str | list[str] | None = None

    @model_validator(mode="after")
    def validate_file_assert_paths(self) -> "StepAssert":
        """Reject absolute paths and parent-directory traversal in file asserts."""
        _validate_assert_paths(self.file_exists, "file_exists")
        _validate_assert_paths(self.file_not_exists, "file_not_exists")
        _validate_assert_paths(self.file_not_empty, "file_not_empty")
        return self


class StepDefinition(BaseModel):
    """Single model for catalog step blueprints, workflow steps, and task steps."""

    model_config = {"extra": "forbid", "strict": True, "populate_by_name": True}

    id: str
    uses: str | None = None
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")
    run: str | None = None
    name: str | None = None
    type: StepType | None = None
    description: str | None = None
    command: str | None = None
    prompt: str | None = None
    script_path: str | None = None
    tools: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=DEFAULT_STEP_TIMEOUT_SECONDS, gt=0)
    assert_: StepAssert | None = Field(default=None, alias="assert")
    on_failure: FailureSpec = Field(default_factory=lambda: FailureSpec(action=FailurePolicy.ABORT))

    @field_validator("type", mode="before")
    @classmethod
    def coerce_type(cls, val: Any) -> Any:
        """Coerce YAML/JSON strings to StepType (strict mode skips enum coercion)."""
        if isinstance(val, str):
            try:
                return StepType(val)
            except ValueError:
                pass
        return val

    @field_validator("on_failure", mode="before")
    @classmethod
    def coerce_on_failure(cls, val: Any) -> Any:
        """Accept bare 'abort' string or full {action, max_retries, backoff_ms, on_max_retries} object."""
        return {"action": val} if isinstance(val, str) else val

    @model_validator(mode="after")
    def validate_step_shape(self) -> "StepDefinition":
        """Enforce exactly one of run/uses/inline-type mode; with_ requires uses."""
        run_incompatible = ("uses", "with_", "command", "type", "prompt", "script_path", "tools")

        if self.with_ and self.uses is None:
            raise ValueError(f"Step '{self.id}': 'with' requires 'uses' to be set.")

        if self.run is not None:
            conflicting = [f for f in run_incompatible if getattr(self, f)]
            if conflicting:
                raise ValueError(f"Step '{self.id}': 'run' cannot be combined with {', '.join(conflicting)}.")
        elif self.uses is not None:
            pass  # with_ overrides resolved at load/execution time
        elif self.type is not None:
            if self.type == StepType.COMMAND and not self.command:
                raise ValueError("Command steps must specify a non-empty 'command' string.")
            if self.type == StepType.AGENT and not self.prompt:
                raise ValueError("Agent steps must specify a non-empty 'prompt' string.")
            if self.type == StepType.SCRIPT and not self.script_path:
                raise ValueError("Script steps must specify a non-empty 'script_path' string.")
        else:
            raise ValueError(f"Step '{self.id}' must specify one of 'run', 'uses', or 'type'.")
        return self


class LoopStepBlock(BaseModel):
    """Loop block step execution definition."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    id: str = Field(min_length=1)
    type: Literal["loop"]
    max_iterations: int = Field(default=5, ge=1)
    until: list[str] = Field(min_length=1)
    do: list[StepDefinition] = Field(min_length=1)
    on_max_iterations: str | dict[str, Any] = "prompt_user"
