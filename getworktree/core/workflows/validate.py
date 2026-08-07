"""Non-raising full workflow definition validation engine."""

from __future__ import annotations

from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from getworktree.common.schema_validation import SchemaValidator
from getworktree.core.workflows.exceptions import (
    WorkflowLoadError,
    WorkflowValidationError,
)
from getworktree.core.workflows.models import WorkflowDefinition

WORKFLOW_VALIDATOR = SchemaValidator(
    resources.files("getworktree.schemas.v1") / "workflow.json"
)


class WorkflowValidationStatus(StrEnum):
    """Classified outcomes for validating one workflow YAML definition."""

    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    NOT_A_FILE = "not_a_file"
    UNREADABLE = "unreadable"
    MALFORMED_YAML = "malformed_yaml"
    ROOT_NOT_MAPPING = "root_not_mapping"


class WorkflowValidationResult(BaseModel):
    """Non-raising result of structural + semantic workflow validation."""

    model_config = {"extra": "forbid", "strict": True}

    status: WorkflowValidationStatus
    source_path: Path
    raw: dict[str, Any] | None = None
    workflow: WorkflowDefinition | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when the workflow definition is fully valid."""
        return self.status == WorkflowValidationStatus.VALID


def _resolve_source_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def _semantic_errors(workflow: WorkflowDefinition) -> list[str]:
    """Return semantic errors after schema success (defensive bounds)."""
    errors: list[str] = []

    if workflow.timeout_seconds is not None and workflow.timeout_seconds < 1:
        errors.append("timeout_seconds must be >= 1 (WORKFLOW_SEM_TIMEOUT).")

    return errors


def validate_workflow_document(
    raw: dict[str, Any],
    *,
    source_path: Path,
) -> WorkflowValidationResult:
    """Schema + semantic + model map without reading disk.

    Args:
        raw: Parsed YAML mapping.
        source_path: Identity path stored on the result (not required to exist).

    Returns:
        Classified ``WorkflowValidationResult``.
    """
    path = Path(source_path)
    validation = WORKFLOW_VALIDATOR.validate(raw)
    if not validation.ok:
        lines = ["Workflow schema validation failed (WORKFLOW_INVALID_SCHEMA):"]
        lines.extend(f"- {msg}" for msg in validation.errors)
        return WorkflowValidationResult(
            status=WorkflowValidationStatus.INVALID,
            source_path=path,
            raw=raw,
            errors=["\n".join(lines)],
        )

    try:
        workflow = WorkflowDefinition.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError and similar
        return WorkflowValidationResult(
            status=WorkflowValidationStatus.INVALID,
            source_path=path,
            raw=raw,
            errors=[f"Workflow model mapping failed (WORKFLOW_INVALID_MODEL): {exc}"],
        )

    semantic = _semantic_errors(workflow)
    if semantic:
        return WorkflowValidationResult(
            status=WorkflowValidationStatus.INVALID,
            source_path=path,
            raw=raw,
            errors=semantic,
        )

    return WorkflowValidationResult(
        status=WorkflowValidationStatus.VALID,
        source_path=path,
        raw=raw,
        workflow=workflow,
        errors=[],
        warnings=[],
    )


def validate_workflow_result(path: Path) -> WorkflowValidationResult:
    """Load and validate one workflow file without raising.

    Primary validation surface for full ``workflow_v1`` checks. Does not print,
    exit, create, or mutate workflow files.

    Args:
        path: Workflow definition path (absolute preferred).

    Returns:
        Classified ``WorkflowValidationResult`` with resolved ``source_path``.
    """
    source_path = _resolve_source_path(path)

    if source_path.exists() and not source_path.is_file():
        return WorkflowValidationResult(
            status=WorkflowValidationStatus.NOT_A_FILE,
            source_path=source_path,
            errors=[
                f"Workflow path exists but is not a regular file: '{source_path}' "
                f"(WORKFLOW_INVALID_NOT_A_FILE).\n"
                "Fix:\n"
                "- point the path at a workflow YAML file, not a directory"
            ],
        )

    if not source_path.exists():
        return WorkflowValidationResult(
            status=WorkflowValidationStatus.NOT_FOUND,
            source_path=source_path,
            errors=[
                f"Workflow definition not found at '{source_path}' "
                f"(WORKFLOW_INVALID_NOT_FOUND).\n"
                "Fix:\n"
                "- run `wt workflow list` to see available workflows\n"
                "- create the definition file or fix the path"
            ],
        )

    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        return WorkflowValidationResult(
            status=WorkflowValidationStatus.UNREADABLE,
            source_path=source_path,
            errors=[
                f"Unable to read workflow definition at '{source_path}': {exc} "
                f"(WORKFLOW_INVALID_UNREADABLE).\n"
                "Fix:\n"
                "- check file permissions and that the path is readable"
            ],
        )

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return WorkflowValidationResult(
            status=WorkflowValidationStatus.MALFORMED_YAML,
            source_path=source_path,
            errors=[
                f"Malformed workflow YAML at '{source_path}': {exc} "
                f"(WORKFLOW_INVALID_MALFORMED_YAML).\n"
                "Fix:\n"
                "- repair YAML syntax, or restore the definition from a template"
            ],
        )

    if not isinstance(parsed, dict):
        return WorkflowValidationResult(
            status=WorkflowValidationStatus.ROOT_NOT_MAPPING,
            source_path=source_path,
            errors=[
                f"Workflow YAML root must be a mapping at '{source_path}' "
                f"(WORKFLOW_INVALID_ROOT_NOT_MAPPING).\n"
                "Fix:\n"
                "- ensure the file is a YAML object, not an array or scalar"
            ],
        )

    return validate_workflow_document(parsed, source_path=source_path)


def load_workflow_definition(path: Path) -> WorkflowDefinition:
    """Return ``WorkflowDefinition`` or raise with classified message.

    Args:
        path: Workflow definition path.

    Returns:
        Typed ``WorkflowDefinition``.

    Raises:
        FileNotFoundError: When the file is missing.
        OSError: When the path cannot be read.
        WorkflowLoadError: For malformed YAML syntax.
        WorkflowValidationError: For other classified validation failures.
    """
    result = validate_workflow_result(path)
    if result.status == WorkflowValidationStatus.VALID:
        assert result.workflow is not None
        return result.workflow
    if result.status == WorkflowValidationStatus.NOT_FOUND:
        raise FileNotFoundError(
            result.errors[0] if result.errors else str(result.status)
        )
    if result.status == WorkflowValidationStatus.UNREADABLE:
        raise OSError(result.errors[0] if result.errors else str(result.status))
    if result.status == WorkflowValidationStatus.MALFORMED_YAML:
        raise WorkflowLoadError(
            result.errors[0] if result.errors else str(result.status)
        )
    raise WorkflowValidationError(
        result.errors[0] if result.errors else str(result.status)
    )


def validate_workflow_inputs(
    workflow: WorkflowDefinition,
    provided_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve workflow inputs against declarations, enforcing required inputs and applying defaults.

    Args:
        workflow: Validated workflow definition.
        provided_inputs: Optional dictionary of supplied execution inputs.

    Returns:
        Merged input dictionary with defaults applied.

    Raises:
        WorkflowValidationError: If a required input is missing without a default.
    """
    provided = provided_inputs or {}
    resolved: dict[str, Any] = {}

    for input_id, decl in workflow.inputs.items():
        if input_id in provided:
            resolved[input_id] = provided[input_id]
        elif decl.default is not None:
            resolved[input_id] = decl.default
        elif decl.required:
            raise WorkflowValidationError(
                f"Missing required input parameter: '{input_id}'"
            )

    return resolved
