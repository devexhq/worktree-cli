"""Parse minimal loop list metadata from a single YAML definition file."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

LOOP_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class LoopMetadataStatus(StrEnum):
    """Classified outcomes for minimal loop metadata parsing."""

    OK = "ok"
    NOT_FOUND = "not_found"
    NOT_A_FILE = "not_a_file"
    UNREADABLE = "unreadable"
    MALFORMED_YAML = "malformed_yaml"
    ROOT_NOT_MAPPING = "root_not_mapping"
    INVALID_METADATA = "invalid_metadata"


class LoopListMetadata(BaseModel):
    """Minimal identity fields used by loop list inventory."""

    model_config = {"extra": "forbid", "strict": True}

    version: int
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_path: Path


class LoopMetadataParseResult(BaseModel):
    """Non-raising result of parsing one loop YAML for list metadata."""

    model_config = {"extra": "forbid", "strict": True}

    status: LoopMetadataStatus
    source_path: Path
    metadata: LoopListMetadata | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when minimal metadata parsed successfully."""
        return self.status == LoopMetadataStatus.OK


def _resolve_source_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def _validate_minimal_fields(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if "version" not in raw:
        errors.append("LOOP_META_MISSING_VERSION: missing required field 'version'")
    else:
        version = raw["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version != 1:
            errors.append("LOOP_META_INVALID_VERSION: version must be integer 1")

    if "name" not in raw:
        errors.append("LOOP_META_MISSING_NAME: missing required field 'name'")
    else:
        name = raw["name"]
        if (
            not isinstance(name, str)
            or name == ""
            or not LOOP_NAME_PATTERN.fullmatch(name)
        ):
            errors.append(
                f"LOOP_META_INVALID_NAME: name must match {LOOP_NAME_PATTERN.pattern}"
            )

    if "description" not in raw:
        errors.append(
            "LOOP_META_MISSING_DESCRIPTION: missing required field 'description'"
        )
    else:
        description = raw["description"]
        if not isinstance(description, str) or len(description) < 1:
            errors.append(
                "LOOP_META_INVALID_DESCRIPTION: description must be a non-empty string"
            )

    return errors


def parse_loop_metadata(path: Path) -> LoopMetadataParseResult:
    """Parse minimal list metadata from one loop YAML file.

    Non-raising primary API. Reads UTF-8 text, loads a single YAML document
    with ``yaml.safe_load``, and validates only ``version``, ``name``, and
    ``description``. Does not run full ``loop_v1`` schema validation, print,
    exit, or mutate files.

    Args:
        path: Loop definition path (absolute preferred).

    Returns:
        Classified ``LoopMetadataParseResult`` with absolute ``source_path``.
    """
    source_path = _resolve_source_path(path)

    if source_path.exists() and not source_path.is_file():
        return LoopMetadataParseResult(
            status=LoopMetadataStatus.NOT_A_FILE,
            source_path=source_path,
            errors=[
                f"Loop path exists but is not a regular file: "
                f"'{source_path}' (LOOP_META_NOT_A_FILE)."
            ],
        )

    if not source_path.exists():
        return LoopMetadataParseResult(
            status=LoopMetadataStatus.NOT_FOUND,
            source_path=source_path,
            errors=[
                f"Loop definition not found at '{source_path}' (LOOP_META_NOT_FOUND)."
            ],
        )

    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        return LoopMetadataParseResult(
            status=LoopMetadataStatus.UNREADABLE,
            source_path=source_path,
            errors=[
                f"Unable to read loop definition at '{source_path}': "
                f"{exc} (LOOP_META_UNREADABLE)."
            ],
        )

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return LoopMetadataParseResult(
            status=LoopMetadataStatus.MALFORMED_YAML,
            source_path=source_path,
            errors=[
                f"Malformed loop YAML at '{source_path}': "
                f"{exc} (LOOP_META_MALFORMED_YAML)."
            ],
        )

    if not isinstance(parsed, dict):
        return LoopMetadataParseResult(
            status=LoopMetadataStatus.ROOT_NOT_MAPPING,
            source_path=source_path,
            errors=[
                f"Loop YAML root must be a mapping at "
                f"'{source_path}' (LOOP_META_ROOT_NOT_MAPPING)."
            ],
        )

    field_errors = _validate_minimal_fields(parsed)
    if field_errors:
        return LoopMetadataParseResult(
            status=LoopMetadataStatus.INVALID_METADATA,
            source_path=source_path,
            errors=field_errors,
        )

    return LoopMetadataParseResult(
        status=LoopMetadataStatus.OK,
        source_path=source_path,
        metadata=LoopListMetadata(
            version=parsed["version"],
            name=parsed["name"],
            description=parsed["description"],
            source_path=source_path,
        ),
    )
