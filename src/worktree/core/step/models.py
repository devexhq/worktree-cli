import copy
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:/")
DEFAULT_STEP_TIMEOUT_SECONDS = 120


class FailurePolicy(StrEnum):
    """Canonical failure-handling vocabulary shared by steps and loop blocks."""

    ABORT = "abort"
    CONTINUE = "continue"
    PROMPT_USER = "prompt_user"
    RETRY = "retry"

    @classmethod
    def context(cls, name: str) -> frozenset["FailurePolicy"]:
        """Return the allowed FailurePolicy subset for a given usage context."""
        if name == "terminal":
            return frozenset({cls.ABORT, cls.CONTINUE, cls.PROMPT_USER})
        return frozenset(cls)


class FailureSpec(BaseModel):
    """Normalized on_failure directive: action, retry tuning, and post-retry escalation."""

    model_config = {"extra": "forbid"}

    action: FailurePolicy
    max_retries: int = Field(default=3, ge=1)
    backoff_ms: int = Field(default=0, ge=0)
    on_max_retries: FailurePolicy = FailurePolicy.ABORT

    @field_validator("action", "on_max_retries", mode="before")
    @classmethod
    def parse_policy(cls, val: Any) -> Any:
        """Coerce string values to FailurePolicy enum instances."""
        if isinstance(val, str):
            try:
                return FailurePolicy(val)
            except ValueError:
                pass
        return val

    @model_validator(mode="after")
    def validate_on_max_retries_context(self) -> "FailureSpec":
        """on_max_retries must be terminal (no RETRY-on-RETRY-exhaustion)."""
        allowed = FailurePolicy.context("terminal")
        if self.on_max_retries not in allowed:
            raise ValueError(f"on_max_retries must be one of {sorted(allowed)}, got {self.on_max_retries!r}.")
        return self


def _coerce_on_failure_value(val: Any) -> Any:
    """Accept bare policy string or full FailureSpec object payload."""
    if val is None:
        return None
    return {"action": val} if isinstance(val, str) else val


class BlueprintDefaults(BaseModel):
    """Optional task/workflow blueprint defaults applied fill-if-omitted to steps."""

    model_config = {"extra": "forbid"}

    on_failure: FailureSpec | None = None

    @field_validator("on_failure", mode="before")
    @classmethod
    def coerce_on_failure(cls, val: Any) -> Any:
        """Match StepDefinition.on_failure string-or-object coercion."""
        return _coerce_on_failure_value(val)


def apply_on_failure_default(
    step_data: dict[str, Any],
    on_failure_default: Any | None,
) -> dict[str, Any]:
    """Copy blueprint ``on_failure`` onto a step dict when the step omits it.

    Fill-if-omitted only: an explicit step ``on_failure`` is never merged or
    replaced. Loop blocks are left unchanged (nested ``do`` fill is separate).
    """
    if on_failure_default is None or "on_failure" in step_data:
        return step_data
    if step_data.get("type") == "loop":
        return step_data

    filled = dict(step_data)
    if isinstance(on_failure_default, FailureSpec):
        filled["on_failure"] = on_failure_default.model_dump(mode="json")
    else:
        filled["on_failure"] = copy.deepcopy(on_failure_default)
    return filled


def extract_defaults_on_failure(raw_defaults: Any) -> Any | None:
    """Return raw ``defaults.on_failure`` from a blueprint payload, if present."""
    if raw_defaults is None:
        return None
    if isinstance(raw_defaults, BlueprintDefaults):
        return raw_defaults.on_failure
    if isinstance(raw_defaults, dict):
        return raw_defaults.get("on_failure")
    return None


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


class AssertionResult(BaseModel):
    """Aggregate result of evaluating a step's assert block."""

    model_config = {"extra": "forbid", "strict": True}

    passed: bool
    failed_conditions: list[str] = Field(default_factory=list)
    message: str


def _validate_run_shape(step: "StepDefinition") -> None:
    """Reject 'run' combined with any uses/inline-type-mode-only fields."""
    run_incompatible = ("uses", "command", "type", "prompt", "script_path", "tools")
    conflicting = [f for f in run_incompatible if getattr(step, f)]
    if conflicting:
        raise ValueError(f"Step '{step.id}': 'run' cannot be combined with {', '.join(conflicting)}.")


def _validate_inline_type_shape(step: "StepDefinition") -> None:
    """Require the field matching the step's inline 'type'."""
    if step.type == StepType.COMMAND and not step.command:
        raise ValueError("Command steps must specify a non-empty 'command' string.")
    if step.type == StepType.AGENT and not step.prompt:
        raise ValueError("Agent steps must specify a non-empty 'prompt' string.")
    if step.type == StepType.SCRIPT and not step.script_path:
        raise ValueError("Script steps must specify a non-empty 'script_path' string.")


class StepDefinition(BaseModel):
    """Single model for catalog step blueprints, workflow steps, and task steps."""

    model_config = {"extra": "forbid", "strict": True, "populate_by_name": True}

    id: str
    uses: str | None = None
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
        return _coerce_on_failure_value(val)

    @model_validator(mode="after")
    def validate_step_shape(self) -> "StepDefinition":
        """Enforce exactly one of run/uses/inline-type mode."""
        if self.run is not None:
            _validate_run_shape(self)
        elif self.uses is not None:
            pass  # resolved to a concrete step at load/execution time
        elif self.type is not None:
            _validate_inline_type_shape(self)
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
    on_max_iterations: FailurePolicy = FailurePolicy.PROMPT_USER

    @field_validator("on_max_iterations", mode="before")
    @classmethod
    def coerce_on_max_iterations(cls, val: Any) -> Any:
        """Coerce string value to FailurePolicy enum instance."""
        if isinstance(val, str):
            try:
                return FailurePolicy(val)
            except ValueError:
                pass
        return val

    @model_validator(mode="after")
    def validate_on_max_iterations_context(self) -> "LoopStepBlock":
        """Reject FailurePolicy values not valid for the terminal context (e.g. RETRY)."""
        allowed = FailurePolicy.context("terminal")
        if self.on_max_iterations not in allowed:
            raise ValueError(f"Loop '{self.id}': on_max_iterations must be one of {sorted(allowed)}.")
        return self


class StepMetadata(BaseModel):
    """Execution metadata for the current step."""

    model_config = {"extra": "forbid", "strict": True}

    id: str
    name: str = ""
    index: int = Field(ge=1)
    attempt: int = Field(default=1, ge=1)


class TaskMetadata(BaseModel):
    """Execution metadata for the parent task (if any)."""

    model_config = {"extra": "forbid", "strict": True}

    name: str = ""
    sha: str = ""


class WorkflowMetadata(BaseModel):
    """Execution metadata for the parent workflow (if any)."""

    model_config = {"extra": "forbid", "strict": True}

    name: str = ""
    sha: str = ""


class PreviousStepMetadata(BaseModel):
    """Execution metadata for the immediately prior step (if any)."""

    model_config = {"extra": "forbid", "strict": True}

    id: str = ""
    name: str = ""
    index: str = ""
    status: str = ""
    exit_code: str = ""


class ExecutionIdentity(BaseModel):
    """Optional run-level task or workflow identity passed into RunContext."""

    model_config = {"extra": "forbid", "strict": True}

    task_name: str = ""
    task_sha: str = ""
    workflow_name: str = ""
    workflow_sha: str = ""


class ExecutionMetadata(BaseModel):
    """Structured metadata exposed to step execution (env + interpolation)."""

    model_config = {"extra": "forbid", "strict": True}

    step: StepMetadata
    task: TaskMetadata = Field(default_factory=TaskMetadata)
    workflow: WorkflowMetadata = Field(default_factory=WorkflowMetadata)
    previous_step: PreviousStepMetadata = Field(default_factory=PreviousStepMetadata)
    steps: list[PreviousStepMetadata] = Field(default_factory=list)


class StepDispatchOutcome(BaseModel):
    """Raw outcome of one or more step primitive dispatches (before finalization)."""

    model_config = {"extra": "forbid", "strict": True}

    status: str  # "completed" | "failed"
    exit_code: int
    stdout: str
    stderr: str
    error_message: str | None = None
    attempts: int = 1


class StepResult(BaseModel):
    """Normalized result of a step execution."""

    model_config = {"extra": "forbid", "strict": True}

    step_id: str
    status: str  # "completed" | "failed" | "ignored"
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    attempts: int = 1
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        """Return True if step finished successfully or was ignored."""
        return self.status in ("completed", "ignored")
