"""Class handle that loads and inspects a task or workflow blueprint."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from worktree.core.blueprint.exceptions import (
    BlueprintLoadError,
    BlueprintNotFoundError,
    BlueprintValidationError,
)
from worktree.core.blueprint.models import BlueprintDefinition, BlueprintKind
from worktree.core.catalog import Catalog, CatalogFileNotFoundError, CatalogResolveStatus, CatalogYamlError
from worktree.core.db import CatalogItemType
from worktree.core.inputs import ParameterInput
from worktree.core.step import LoopStepBlock, StepDefinition


class Blueprint:
    """Load, inspect, and dump a unified task/workflow document."""

    spec: ClassVar[type[BlueprintDefinition]] = BlueprintDefinition
    _KIND_FROM_ITEM_TYPE: ClassVar[dict[CatalogItemType, BlueprintKind]] = {
        CatalogItemType.TASK: BlueprintKind.TASK,
        CatalogItemType.WORKFLOW: BlueprintKind.WORKFLOW,
    }
    _KIND_FROM_FOLDER: ClassVar[dict[str, BlueprintKind]] = {
        "tasks": BlueprintKind.TASK,
        "workflows": BlueprintKind.WORKFLOW,
    }

    def __init__(self, instance: BlueprintDefinition) -> None:
        self._instance = instance

    @classmethod
    def load(cls, name: str, catalog: Catalog | None = None) -> Blueprint:
        """Build a handle from a catalog task/workflow name or SHA."""
        result = (catalog or Catalog()).resolve(name)
        if result.status == CatalogResolveStatus.NOT_FOUND:
            raise BlueprintNotFoundError(f"Blueprint '{name}' not found in catalog.")
        if result.status == CatalogResolveStatus.LOAD_ERROR or result.raw is None or result.record is None:
            detail = "; ".join(result.errors) if result.errors else "no YAML object"
            raise BlueprintLoadError(f"Failed to load blueprint '{name}' from catalog: {detail}")
        kind = cls._kind_from_item_type(result.record.item_type)
        return cls(cls.spec.from_document(result.raw, kind=kind))

    @classmethod
    def from_path(cls, path: Path) -> Blueprint:
        """Build a handle from a YAML file, inferring kind from a parent folder."""
        resolved = path.resolve()
        kind = cls._kind_from_path(resolved)
        try:
            raw = Catalog.read_yaml(resolved)
        except (CatalogFileNotFoundError, CatalogYamlError) as exc:
            raise BlueprintLoadError(f"Failed to load blueprint from '{resolved}': {exc}") from exc
        return cls(cls.spec.from_document(raw, kind=kind))

    @property
    def kind(self) -> BlueprintKind:
        """Return the derived task/workflow kind."""
        return self._instance.kind

    @property
    def name(self) -> str:
        """Return the blueprint name."""
        return self._instance.name

    @property
    def steps(self) -> list[StepDefinition | LoopStepBlock]:
        """Return the live steps list from the wrapped document."""
        return self._instance.steps

    @property
    def inputs(self) -> dict[str, ParameterInput]:
        """Return the live inputs mapping from the wrapped document."""
        return self._instance.inputs

    def dump(self) -> dict[str, object]:
        """Return the in-memory document as a JSON-mode dict, including derived kind."""
        return self._instance.model_dump(mode="json")

    @classmethod
    def _kind_from_item_type(cls, item_type: CatalogItemType) -> BlueprintKind:
        """Map a catalog item type to a blueprint kind, or raise."""
        kind = cls._KIND_FROM_ITEM_TYPE.get(item_type)
        if kind is None:
            raise BlueprintValidationError(f"Cannot derive blueprint kind from catalog item type '{item_type}'.")
        return kind

    @classmethod
    def _kind_from_path(cls, path: Path) -> BlueprintKind:
        """Infer kind from the nearest ``tasks`` or ``workflows`` ancestor folder."""
        for parent in path.parents:
            kind = cls._KIND_FROM_FOLDER.get(parent.name)
            if kind is not None:
                return kind
        raise BlueprintValidationError(
            f"Cannot infer blueprint kind from path '{path}'; expected a parent 'tasks/' or 'workflows/' segment."
        )
