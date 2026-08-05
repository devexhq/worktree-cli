"""Non-raising full loop definition validation engine."""

from __future__ import annotations

from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from getworktree.common.schema_validation import SchemaValidator
from getworktree.core.loops.models import LoopDefinition

LOOP_VALIDATOR = SchemaValidator(
    resources.files("getworktree.schemas") / "loop_v1.json"
)


class LoopValidationStatus(StrEnum):
    """Classified outcomes for validating one loop YAML definition."""

    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    NOT_A_FILE = "not_a_file"
    UNREADABLE = "unreadable"
    MALFORMED_YAML = "malformed_yaml"
    ROOT_NOT_MAPPING = "root_not_mapping"


class LoopValidationResult(BaseModel):
    """Non-raising result of structural + semantic loop validation."""

    model_config = {"extra": "forbid", "strict": True}

    status: LoopValidationStatus
    source_path: Path
    raw: dict[str, Any] | None = None
    loop: LoopDefinition | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when the loop definition is fully valid."""
        return self.status == LoopValidationStatus.VALID


def _resolve_source_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def _semantic_errors(loop: LoopDefinition) -> list[str]:
    """Return semantic errors after schema success (defensive bounds)."""
    errors: list[str] = []

    if loop.iteration.max_attempts < 1:
        errors.append("iteration.max_attempts must be >= 1 (LOOP_SEM_MAX_ATTEMPTS).")

    if loop.trigger.timeout_seconds < 1 or loop.agent.timeout_seconds < 1:
        errors.append(
            "trigger.timeout_seconds and agent.timeout_seconds must be >= 1 "
            "(LOOP_SEM_TIMEOUT)."
        )

    if loop.patch.max_files < 1 or loop.patch.max_patch_kb < 1:
        errors.append(
            "patch.max_files and patch.max_patch_kb must be >= 1 "
            "(LOOP_SEM_PATCH_LIMIT)."
        )

    if len(loop.iteration.stop_when) < 1:
        errors.append(
            "iteration.stop_when must contain at least one value "
            "(LOOP_SEM_STOP_WHEN_EMPTY)."
        )

    return errors


def validate_loop_document(
    raw: dict[str, Any],
    *,
    source_path: Path,
) -> LoopValidationResult:
    """Schema + semantic + model map without reading disk.

    Args:
        raw: Parsed YAML mapping.
        source_path: Identity path stored on the result (not required to exist).

    Returns:
        Classified ``LoopValidationResult``.
    """
    path = Path(source_path)
    validation = LOOP_VALIDATOR.validate(raw)
    if not validation.ok:
        lines = ["Loop schema validation failed (LOOP_INVALID_SCHEMA):"]
        lines.extend(f"- {msg}" for msg in validation.errors)
        return LoopValidationResult(
            status=LoopValidationStatus.INVALID,
            source_path=path,
            raw=raw,
            errors=["\n".join(lines)],
        )

    try:
        loop = LoopDefinition.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError and similar
        return LoopValidationResult(
            status=LoopValidationStatus.INVALID,
            source_path=path,
            raw=raw,
            errors=[f"Loop model mapping failed (LOOP_INVALID_MODEL): {exc}"],
        )

    semantic = _semantic_errors(loop)
    if semantic:
        return LoopValidationResult(
            status=LoopValidationStatus.INVALID,
            source_path=path,
            raw=raw,
            errors=semantic,
        )

    return LoopValidationResult(
        status=LoopValidationStatus.VALID,
        source_path=path,
        raw=raw,
        loop=loop,
        errors=[],
        warnings=[],
    )


def validate_loop_result(path: Path) -> LoopValidationResult:
    """Load and validate one loop file without raising.

    Primary validation surface for full ``loop_v1`` checks. Does not print,
    exit, create, or mutate loop files.

    Args:
        path: Loop definition path (absolute preferred).

    Returns:
        Classified ``LoopValidationResult`` with resolved ``source_path``.
    """
    source_path = _resolve_source_path(path)

    if source_path.exists() and not source_path.is_file():
        return LoopValidationResult(
            status=LoopValidationStatus.NOT_A_FILE,
            source_path=source_path,
            errors=[
                f"Loop path exists but is not a regular file: '{source_path}' "
                f"(LOOP_INVALID_NOT_A_FILE).\n"
                "Fix:\n"
                "- point the path at a loop YAML file, not a directory"
            ],
        )

    if not source_path.exists():
        return LoopValidationResult(
            status=LoopValidationStatus.NOT_FOUND,
            source_path=source_path,
            errors=[
                f"Loop definition not found at '{source_path}' "
                f"(LOOP_INVALID_NOT_FOUND).\n"
                "Fix:\n"
                "- run `wt workflow list` to see available workflows\n"
                "- create the definition file or fix the path"
            ],
        )

    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        return LoopValidationResult(
            status=LoopValidationStatus.UNREADABLE,
            source_path=source_path,
            errors=[
                f"Unable to read loop definition at '{source_path}': {exc} "
                f"(LOOP_INVALID_UNREADABLE).\n"
                "Fix:\n"
                "- check file permissions and that the path is readable"
            ],
        )

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return LoopValidationResult(
            status=LoopValidationStatus.MALFORMED_YAML,
            source_path=source_path,
            errors=[
                f"Malformed loop YAML at '{source_path}': {exc} "
                f"(LOOP_INVALID_MALFORMED_YAML).\n"
                "Fix:\n"
                "- repair YAML syntax, or restore the definition from a template"
            ],
        )

    if not isinstance(parsed, dict):
        return LoopValidationResult(
            status=LoopValidationStatus.ROOT_NOT_MAPPING,
            source_path=source_path,
            errors=[
                f"Loop YAML root must be a mapping at '{source_path}' "
                f"(LOOP_INVALID_ROOT_NOT_MAPPING).\n"
                "Fix:\n"
                "- ensure the file is a YAML object, not an array or scalar"
            ],
        )

    return validate_loop_document(parsed, source_path=source_path)


def load_loop_definition(path: Path) -> LoopDefinition:
    """Return ``LoopDefinition`` or raise with classified message.

    Args:
        path: Loop definition path.

    Returns:
        Typed ``LoopDefinition``.

    Raises:
        FileNotFoundError: When the file is missing.
        OSError: When the path cannot be read.
        ValueError: For other classified validation failures.
    """
    result = validate_loop_result(path)
    if result.status == LoopValidationStatus.VALID:
        assert result.loop is not None
        return result.loop
    if result.status == LoopValidationStatus.NOT_FOUND:
        raise FileNotFoundError(
            result.errors[0] if result.errors else str(result.status)
        )
    if result.status == LoopValidationStatus.UNREADABLE:
        raise OSError(result.errors[0] if result.errors else str(result.status))
    raise ValueError(result.errors[0] if result.errors else str(result.status))
