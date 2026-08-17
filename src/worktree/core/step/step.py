"""Class handle that loads a StepDefinition and executes one step."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import ValidationError

from worktree.core.catalog import Catalog, CatalogResolveStatus
from worktree.core.inputs import interpolate_step_fields
from worktree.core.step.exceptions import StepNotFoundError, StepValidationError
from worktree.core.step.models import StepDefinition
from worktree.core.step.runner import StepResult, execute_step


class Step:
    """Load, dump, and execute a single ``StepDefinition``."""

    spec: ClassVar[type[StepDefinition]] = StepDefinition

    def __init__(self, instance: StepDefinition) -> None:
        self._instance = instance

    @classmethod
    def load(
        cls,
        source: str | dict[str, Any] | StepDefinition,
        catalog: Catalog | None = None,
    ) -> Step:
        """Build a handle from a model, raw dict, or catalog name/SHA."""
        if isinstance(source, StepDefinition):
            return cls(source)
        if isinstance(source, dict):
            return cls(cls._validated_definition(source, source_name="dict"))
        return cls._load_from_catalog(source, catalog)

    @property
    def id(self) -> str:
        """Return the wrapped step identifier."""
        return self._instance.id

    def dump(self) -> dict[str, Any]:
        """Return the authored step document as JSON-mode dict."""
        return self._instance.model_dump(mode="json")

    def execute(
        self,
        sandbox_path: Path,
        *,
        inputs: dict[str, str | int | bool] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StepResult:
        """Interpolate ``inputs`` then run the existing ``execute_step`` runner."""
        ready = self._interpolated(inputs or {})
        merged_context: dict[str, Any] = {
            **(context or {}),
            **({"inputs": inputs} if inputs is not None else {}),
        }
        return execute_step(ready._instance, sandbox_path, merged_context or None)

    def _interpolated(self, inputs: dict[str, str | int | bool]) -> Step:
        """Return this handle, or a new one with ``inputs`` substituted."""
        if not inputs:
            return self
        return Step(interpolate_step_fields(self._instance, inputs))

    @classmethod
    def _load_from_catalog(cls, name: str, catalog: Catalog | None) -> Step:
        """Resolve a catalog step by name or SHA and validate the YAML object."""
        result = (catalog or Catalog()).resolve_step(name)
        if result.status == CatalogResolveStatus.NOT_FOUND:
            raise StepNotFoundError(f"Step '{name}' not found in catalog.")
        if result.status == CatalogResolveStatus.LOAD_ERROR or result.raw is None:
            detail = "; ".join(result.errors) if result.errors else "no YAML object"
            raise StepValidationError(f"Failed to load step '{name}' from catalog: {detail}")
        return cls(cls._validated_definition(result.raw, source_name=name))

    @classmethod
    def _validated_definition(cls, data: dict[str, Any], *, source_name: str) -> StepDefinition:
        """Validate a mapping as ``StepDefinition`` or raise ``StepValidationError``."""
        try:
            return cls.spec.model_validate(data)
        except (ValidationError, ValueError) as exc:
            raise StepValidationError(f"Step definition validation failed for '{source_name}': {exc}") from exc
