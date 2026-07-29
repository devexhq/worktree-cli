"""JSON Schema validation for Worktree config V1."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator


@dataclass
class ValidationResult:
    """Outcome of validating a config document against the V1 schema."""

    ok: bool
    errors: list[str] = field(default_factory=list)


def _schema_path() -> resources.Traversable:
    return resources.files("getworktree.schemas") / "config_v1.json"


def load_config_v1_schema() -> dict[str, Any]:
    """Load the packaged V1 JSON Schema document."""
    with _schema_path().open(encoding="utf-8") as f:
        return json.load(f)


def validate_config_v1(config: dict[str, Any]) -> ValidationResult:
    """Validate ``config`` against the V1 JSON Schema."""
    schema = load_config_v1_schema()
    validator = Draft202012Validator(schema)
    messages: list[str] = []
    for error in sorted(validator.iter_errors(config), key=lambda e: e.path):
        path = ".".join(str(p) for p in error.path) if error.path else "(root)"
        messages.append(f"{path}: {error.message}")
    return ValidationResult(ok=not messages, errors=messages)
