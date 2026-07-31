"""Shared helpers for validating packaged JSON schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator


@dataclass
class ValidationResult:
    """Outcome of validating a document against a JSON schema."""

    ok: bool
    errors: list[str] = field(default_factory=list)


class SchemaValidator:
    """Validate a document against a packaged JSON schema path."""

    def __init__(self, schema_path: resources.Traversable) -> None:
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
        return ValidationResult(ok=not messages, errors=messages)
