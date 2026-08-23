"""Shared helpers for validating packaged JSON schemas."""

from __future__ import annotations

import json
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Outcome of validating a document against a JSON schema."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if validation succeeded without errors."""
        return not self.errors


class SchemaValidator:
    """Validate a document against a packaged JSON schema path."""

    def __init__(self, schema_path: Traversable) -> None:
        self.schema_path = schema_path

    def validate(self, document: dict[str, Any]) -> ValidationResult:
        """Validate ``document`` against the configured schema."""
        with self.schema_path.open(encoding="utf-8") as handle:
            schema = json.load(handle)

        validator = Draft202012Validator(schema)
        messages: list[str] = []
        for error in sorted(validator.iter_errors(document), key=lambda e: e.path):
            path = ".".join(str(p) for p in error.path) if error.path else "(root)"
            messages.append(f"{path}: {error.message}")
        return ValidationResult(errors=messages)


def _config_schema_path() -> Traversable:
    return resources.files("worktree.schemas.v1") / "config.json"


CONFIG_VALIDATOR = SchemaValidator(_config_schema_path())
