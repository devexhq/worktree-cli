"""JSON Schema validation for Worktree loop V1 definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator


@dataclass
class ValidationResult:
    """Outcome of validating a loop document against the V1 schema."""

    ok: bool
    errors: list[str] = field(default_factory=list)


def _schema_path() -> resources.Traversable:
    return resources.files("getworktree.schemas") / "loop_v1.json"


def load_loop_v1_schema() -> dict[str, Any]:
    """Load the packaged V1 loop schema document."""
    with _schema_path().open(encoding="utf-8") as f:
        return json.load(f)


def validate_loop_v1(loop_obj: dict[str, Any]) -> ValidationResult:
    """Validate ``loop_obj`` against the V1 loop JSON schema."""
    schema = load_loop_v1_schema()
    validator = Draft202012Validator(schema)
    messages: list[str] = []
    for error in sorted(validator.iter_errors(loop_obj), key=lambda e: e.path):
        path = ".".join(str(p) for p in error.path) if error.path else "(root)"
        messages.append(f"{path}: {error.message}")
    return ValidationResult(ok=not messages, errors=messages)
