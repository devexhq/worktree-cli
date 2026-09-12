from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

from worktree.core.blueprint import BlueprintDefinition
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogItem
from worktree.core.db import CatalogRecord
from worktree.core.step import StepDefinition

from .legacy import FileSystem

type CatalogDumpMode = Literal["file_definition"]


class BaseCatalogHelper[DefinitionT: BaseModel]:
    """Build and write a valid catalog definition for tests."""

    fs: FileSystem
    key: str
    instance: DefinitionT
    _catalog_item_path: ClassVar[Path]
    _defaults: ClassVar[dict[str, Any]]

    def __init__(self, *, fs: FileSystem, key: str, **overrides: object) -> None:
        self.fs = fs
        self.key = key
        self.instance = self._definition_class().model_validate({**self._defaults, **overrides})

    @classmethod
    def _definition_class(cls) -> type[DefinitionT]:
        """Return the Pydantic definition type built by this helper."""
        raise NotImplementedError

    @property
    def document(self) -> dict[str, Any]:
        """Return a fresh mutable representation of the catalog file definition."""
        return self.model_dump("file_definition")

    @property
    def catalog_item(self) -> CatalogItem[DefinitionT]:
        """Return the definition paired with its derived catalog identity."""
        return CatalogItem(
            path=self._catalog_item_path / f"{self.key}.yaml",
            definition=self.instance,
        )

    def model_dump(self, dump_mode: CatalogDumpMode = "file_definition") -> dict[str, Any]:
        """Serialize the definition using a named catalog-helper output mode."""
        match dump_mode:
            case "file_definition":
                return self.instance.model_dump(mode="json")

    def create_file(self, filename: str | Path | None = None) -> Path:
        """Write the file definition to its catalog path and return the created path."""
        relative_path = self._catalog_item_path / (filename or f"{self.key}.yaml")
        return self.fs.write_file(Path(".worktree/catalog") / relative_path, self.document)


class BlueprintHelper(BaseCatalogHelper[BlueprintDefinition]):
    """Build blueprint catalog definitions for tests."""

    _catalog_item_path = Path("blueprints")
    _defaults: ClassVar[dict[str, Any]] = {
        "name": "Sample Blueprint",
        "use_sandbox": False,
        "steps": [
            {"id": "step-1", "run": "echo step1"},
            {"id": "step-2", "run": "echo step2", "on_failure": "prompt_user"},
        ],
    }

    @classmethod
    def _definition_class(cls) -> type[BlueprintDefinition]:
        """Return the blueprint definition type."""
        return BlueprintDefinition


class StepHelper(BaseCatalogHelper[StepDefinition]):
    """Build reusable step catalog definitions for tests."""

    _catalog_item_path = Path("steps")
    _defaults: ClassVar[dict[str, Any]] = {
        "id": "step-1",
        "run": "echo step",
    }

    @classmethod
    def _definition_class(cls) -> type[StepDefinition]:
        """Return the reusable step definition type."""
        return StepDefinition


class CatalogHelper:
    """Create typed catalog test definitions rooted at a test filesystem."""

    def __init__(self, fs: FileSystem) -> None:
        self.fs = fs

    def blueprint(self, *, key: str, **overrides: object) -> BlueprintHelper:
        """Build a valid blueprint definition with optional field overrides."""
        return BlueprintHelper(fs=self.fs, key=key, **overrides)

    def step(self, *, key: str, **overrides: object) -> StepHelper:
        """Build a valid reusable step definition with optional field overrides."""
        return StepHelper(fs=self.fs, key=key, **overrides)

    def save[DefinitionT: BaseModel](self, helper: BaseCatalogHelper[DefinitionT]) -> CatalogRecord:
        """Save a helper's file definition through the production catalog facade."""
        item = helper.catalog_item
        return Catalog(self.fs.base_path).save(
            item.key,
            helper.document,
            item_type=item.item_type,
        )
